#!/usr/bin/env python3
"""
ADSBee Console Monitor v3 - Clean interface with help overlay and hex decoding
"""

import socket
import base64
import struct
import sys
import time
from datetime import datetime
import argparse
import select
import threading
import re
from collections import deque
import os
import termios
import tty
import fcntl

# Try to import decoder module
try:
    from adsbee_decoder import ADSBDecoder
    DECODER_AVAILABLE = True
except ImportError:
    DECODER_AVAILABLE = False
    print("Note: Decoder module not found. Hex decoding disabled.")

# ANSI escape codes for terminal control
class ANSI:
    CLEAR = '\033[2J'
    CLEAR_LINE = '\033[2K'
    CURSOR_UP = '\033[1A'
    CURSOR_DOWN = '\033[1B'
    CURSOR_HOME = '\033[H'
    SAVE_CURSOR = '\033[s'
    RESTORE_CURSOR = '\033[u'
    HIDE_CURSOR = '\033[?25l'
    SHOW_CURSOR = '\033[?25h'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    REVERSE = '\033[7m'

    @staticmethod
    def move_cursor(row, col):
        return f'\033[{row};{col}H'

    @staticmethod
    def set_scroll_region(top, bottom):
        return f'\033[{top};{bottom}r'


class ADSBeeWebSocket:
    """WebSocket client for ADSBee console that handles binary frames"""

    def __init__(self, host, port=80):
        self.host = host
        self.port = port
        self.sock = None
        self.connected = False

    def connect(self):
        """Connect and perform WebSocket handshake"""
        # Create socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(5)
        self.sock.connect((self.host, self.port))

        # WebSocket handshake
        key = base64.b64encode(b"ADSBeeMonitor123").decode('ascii')
        handshake = (
            f"GET /console HTTP/1.1\r\n"
            f"Host: {self.host}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"Origin: http://{self.host}\r\n"
            f"\r\n"
        )

        self.sock.send(handshake.encode())

        # Read handshake response
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(1024)
            if not chunk:
                raise Exception("Connection closed during handshake")
            response += chunk

        if b"101 Switching Protocols" not in response:
            raise Exception(f"Handshake failed: {response.decode()}")

        self.connected = True

    def send_text(self, text):
        """Send text message as WebSocket frame"""
        if not self.connected:
            return False

        try:
            payload = text.encode('utf-8')
            frame = self._create_frame(0x1, payload)
            self.sock.send(frame)
            return True
        except:
            return False

    def _create_frame(self, opcode, payload):
        """Create a WebSocket frame"""
        frame = bytearray()
        frame.append(0x80 | opcode)

        length = len(payload)
        if length <= 125:
            frame.append(0x80 | length)
        elif length <= 65535:
            frame.append(0x80 | 126)
            frame.extend(struct.pack('>H', length))
        else:
            frame.append(0x80 | 127)
            frame.extend(struct.pack('>Q', length))

        mask = b'\x37\x42\x13\x99'
        frame.extend(mask)

        for i, byte in enumerate(payload):
            frame.append(byte ^ mask[i % 4])

        return bytes(frame)

    def receive(self, timeout=0.1):
        """Receive and decode WebSocket frame"""
        if not self.connected:
            return None

        ready = select.select([self.sock], [], [], timeout)
        if not ready[0]:
            return ""

        try:
            header = self._recv_exact(2)
            if not header:
                self.connected = False
                return None

            fin = (header[0] & 0x80) != 0
            opcode = header[0] & 0x0f
            masked = (header[1] & 0x80) != 0
            payload_len = header[1] & 0x7f

            if payload_len == 126:
                ext = self._recv_exact(2)
                if not ext:
                    return None
                payload_len = struct.unpack('>H', ext)[0]
            elif payload_len == 127:
                ext = self._recv_exact(8)
                if not ext:
                    return None
                payload_len = struct.unpack('>Q', ext)[0]

            mask = None
            if masked:
                mask = self._recv_exact(4)
                if not mask:
                    return None

            payload = self._recv_exact(payload_len)
            if payload is None:
                return None

            if masked and mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))

            if opcode == 0x1 or opcode == 0x2:  # Text or Binary frame
                return payload.decode('utf-8', errors='ignore')
            elif opcode == 0x8:  # Close frame
                self.connected = False
                return None
            elif opcode == 0x9:  # Ping frame
                self.sock.send(self._create_frame(0xA, payload))
                return ""
            else:
                return ""

        except:
            self.connected = False
            return None

    def _recv_exact(self, n):
        """Receive exactly n bytes"""
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def close(self):
        """Close connection"""
        if self.sock:
            if self.connected:
                try:
                    self.sock.send(self._create_frame(0x8, b""))
                    time.sleep(0.1)
                except:
                    pass
            self.sock.close()
            self.connected = False


class CleanMonitor:
    """Monitor with clean interface and overlay help"""

    def __init__(self, host, filters=None, log_file=None):
        self.ws = ADSBeeWebSocket(host)
        self.host = host
        self.filters = filters or []
        self.log_file = log_file
        self.running = True
        self.paused = False
        self.debug_mode = False
        self.decode_mode = DECODER_AVAILABLE  # Enable decoding if available
        self.show_help_overlay = False
        self.show_stats_overlay = False
        self.input_buffer = ""
        self.command_history = deque(maxlen=50)
        self.history_index = -1
        self.tab_completion_index = -1
        self.tab_suggestions = []
        self.tab_index = -1
        self.original_input = ""

        # Common filter patterns and AT commands for tab completion
        self.common_patterns = [
            'MQTT', 'mqtt', 'ERROR', 'WARNING', 'INFO',
            'Failed', 'Skipped', 'duplicate', 'decode',
            'Feed', 'feed', 'protocol', 'connect', 'broker'
        ]

        self.common_at_commands = [
            'AT+FEED?', 'AT+FEEDPROTOCOL?', 'AT+LOG_LEVEL=INFO',
            'AT+NETWORK_INFO?', 'AT+SETTINGS?', 'AT+FEEDEN?',
            'AT+FEEDPROTOCOL=0,MQTT', 'AT+FEED=0,mqtt://broker.hivemq.com,1883,1,MQTT',
            'AT+MQTTFMT=0,JSON', 'AT+MQTTFMT=0,BINARY',
            'AT+SETTINGS=SAVE', 'AT+REBOOT'
        ]

        # Terminal dimensions
        self.term_height, self.term_width = self.get_terminal_size()
        self.input_height = 2  # Reduced input area height
        self.log_height = self.term_height - self.input_height - 1

        # Message buffer
        self.buffer = deque(maxlen=1000)
        self.display_buffer = deque(maxlen=self.log_height - 1)

        # Statistics
        self.stats = {
            'total_messages': 0,
            'filtered_messages': 0,
            'duplicates': 0,
            'decode_failures': 0,
            'bit_errors': 0,
            'mqtt_messages': 0,
            'commands_sent': 0,
            'icao_addresses': set(),
            'start_time': time.time()
        }

        # Initialize decoder if available
        self.decoder = ADSBDecoder() if DECODER_AVAILABLE else None

        # Regex patterns
        self.patterns = {
            'duplicate': re.compile(r'duplicate packet.*icao=0x([a-f0-9]+)', re.I),
            'decode_fail': re.compile(r'Unable to decode.*ICAO 0x([a-f0-9]+)', re.I),
            'bit_error': re.compile(r'Corrected.*bit error', re.I),
            'mqtt': re.compile(r'MQTT|mqtt|Feed|feed', re.I),
            'icao': re.compile(r'icao=0x([a-f0-9]+)', re.I),
            'error': re.compile(r'ERROR|Failed', re.I),
            'warning': re.compile(r'WARNING|Warning|Skipped', re.I),
            'info': re.compile(r'INFO|Info', re.I)
        }

        # Open log file if specified
        self.log_handle = None
        if self.log_file:
            self.log_handle = open(self.log_file, 'a')
            self.log_handle.write(f"\n{'='*80}\n")
            self.log_handle.write(f"Session started: {datetime.now()}\n")
            self.log_handle.write(f"Host: {host}\n")
            self.log_handle.write(f"{'='*80}\n")

    def get_terminal_size(self):
        """Get terminal dimensions"""
        try:
            rows, cols = os.popen('stty size', 'r').read().split()
            return int(rows), int(cols)
        except:
            return 24, 80

    def setup_terminal(self):
        """Setup terminal for split screen"""
        # Save terminal settings
        self.old_settings = termios.tcgetattr(sys.stdin)

        # Set terminal to raw mode
        tty.setraw(sys.stdin)

        # Make stdin non-blocking
        fd = sys.stdin.fileno()
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        # Clear screen and setup regions
        print(ANSI.CLEAR, end='')
        print(ANSI.CURSOR_HOME, end='')

        # Set scroll region for log area
        print(ANSI.set_scroll_region(1, self.log_height), end='')

        # Draw interface
        self.draw_separator()
        self.draw_input_area()

        sys.stdout.flush()

    def restore_terminal(self):
        """Restore terminal settings"""
        try:
            print(ANSI.set_scroll_region(1, self.term_height), end='')
            print(ANSI.CLEAR, end='')
            print(ANSI.SHOW_CURSOR, end='')
            sys.stdout.flush()
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
        except:
            pass

    def draw_separator(self):
        """Draw separator line between log and input areas"""
        print(ANSI.move_cursor(self.log_height + 1, 1), end='')

        # Build status line
        status = []
        if self.paused:
            status.append("PAUSED")
        if self.debug_mode:
            status.append("DEBUG")
        if self.decode_mode and self.decoder:
            status.append("DECODE")
        if self.filters:
            status.append(f"Filters: {len(self.filters)}")
        else:
            status.append("No Filters")

        status_text = f" {self.host} | {' | '.join(status)} "
        padding = (self.term_width - len(status_text)) // 2
        separator_line = "─" * padding + status_text + "─" * (self.term_width - padding - len(status_text))

        print(f"\033[36m{separator_line}\033[0m", end='')
        sys.stdout.flush()

    def draw_input_area(self):
        """Draw the input area"""
        # Clear input lines
        print(ANSI.move_cursor(self.log_height + 2, 1), end='')
        print(ANSI.CLEAR_LINE, end='')

        # Draw prompt with input
        prompt = "> "
        display_text = self.input_buffer

        # Show tab suggestion if active
        if self.tab_suggestions and self.tab_index >= 0:
            suggestion = self.tab_suggestions[self.tab_index]
            # Show the suggestion in gray after the current input
            common_prefix = os.path.commonprefix([self.original_input, suggestion])
            if len(suggestion) > len(self.original_input):
                completion = suggestion[len(self.original_input):]
                display_text = self.input_buffer + f"\033[90m{completion}\033[0m"

        print(f"\033[32m{prompt}\033[0m{display_text}", end='')

        # Show tab hints if available
        if self.tab_suggestions and len(self.tab_suggestions) > 1:
            hint = f" [{self.tab_index + 1}/{len(self.tab_suggestions)}]"
            print(f"\033[90m{hint}\033[0m", end='')

        # Show quick help on the same line if there's room
        cursor_pos = len(prompt) + len(self.input_buffer) + 2
        if cursor_pos < self.term_width - 30 and not self.tab_suggestions:
            print(ANSI.move_cursor(self.log_height + 2, self.term_width - 28), end='')
            print("\033[90m[F1/? Help] [F2 Stats] [Tab]\033[0m", end='')

        # Position cursor after actual input (not suggestion)
        print(ANSI.move_cursor(self.log_height + 2, len(prompt) + len(self.input_buffer) + 1), end='')
        print(ANSI.SHOW_CURSOR, end='')
        sys.stdout.flush()

    def show_help(self):
        """Display help overlay"""
        help_lines = [
            "╔══════════════════════════════════════════════════════╗",
            "║                  ADSBee Monitor Help                  ║",
            "╠══════════════════════════════════════════════════════╣",
            "║ COMMANDS:                                            ║",
            "║   F1             - Toggle this help                  ║",
            "║   F2             - Show/hide statistics              ║",
            "║   Ctrl+C         - Exit monitor                      ║",
            "║   Ctrl+L         - Clear screen                      ║",
            "║   Ctrl+P         - Pause/resume output               ║",
            "║   Ctrl+D         - Toggle debug mode (no filters)    ║",
            "║   Ctrl+X         - Toggle hex decoding (ICAO/types)  ║",
            "║                                                       ║",
            "║ FILTERS:                                             ║",
            "║   /f <pattern>   - Add filter                        ║",
            "║   /rf <pattern>  - Remove filter                     ║",
            "║   /lf            - List filters                      ║",
            "║   /cf            - Clear all filters                 ║",
            "║                                                       ║",
            "║ AT COMMANDS:                                         ║",
            "║   AT+<command>   - Send AT command                   ║",
            "║   Examples:                                          ║",
            "║     AT+FEED?           - List feeds                  ║",
            "║     AT+FEEDPROTOCOL?   - Show protocols              ║",
            "║     AT+MQTTFMT=0,JSON  - Set MQTT format             ║",
            "║     AT+SETTINGS=SAVE   - Save settings               ║",
            "║     AT+REBOOT          - Reboot device               ║",
            "║                                                       ║",
            "║ Press F1 to close help (? works in commands)         ║",
            "╚══════════════════════════════════════════════════════╝"
        ]

        # Calculate position to center the help box
        box_height = len(help_lines)
        box_width = 58
        start_row = (self.log_height - box_height) // 2
        start_col = (self.term_width - box_width) // 2

        # Draw help box
        for i, line in enumerate(help_lines):
            print(ANSI.move_cursor(start_row + i, start_col), end='')
            print(f"\033[40m\033[97m{line}\033[0m", end='')

        sys.stdout.flush()

    def show_statistics(self):
        """Display statistics overlay"""
        runtime = time.time() - self.stats['start_time']
        hours = int(runtime // 3600)
        minutes = int((runtime % 3600) // 60)
        seconds = int(runtime % 60)

        stats_lines = [
            "╔══════════════════════════════════════════════════════╗",
            "║                    Statistics                         ║",
            "╠══════════════════════════════════════════════════════╣",
            f"║ Runtime:          {hours:02d}:{minutes:02d}:{seconds:02d}                              ║",
            f"║ Total messages:   {self.stats['total_messages']:,}".ljust(56) + "║",
            f"║ Commands sent:    {self.stats['commands_sent']}".ljust(56) + "║",
            f"║ Duplicate packets:{self.stats['duplicates']:,}".ljust(56) + "║",
            f"║ Decode failures:  {self.stats['decode_failures']:,}".ljust(56) + "║",
            f"║ Bit errors fixed: {self.stats['bit_errors']:,}".ljust(56) + "║",
            f"║ MQTT messages:    {self.stats['mqtt_messages']:,}".ljust(56) + "║",
            f"║ Unique aircraft:  {len(self.stats['icao_addresses'])}".ljust(56) + "║",
            "║                                                       ║",
            "║ Press F2 to close                                    ║",
            "╚══════════════════════════════════════════════════════╝"
        ]

        # Calculate position
        box_height = len(stats_lines)
        box_width = 58
        start_row = (self.log_height - box_height) // 2
        start_col = (self.term_width - box_width) // 2

        # Draw stats box
        for i, line in enumerate(stats_lines):
            print(ANSI.move_cursor(start_row + i, start_col), end='')
            print(f"\033[44m\033[97m{line}\033[0m", end='')

        sys.stdout.flush()

    def add_to_log(self, message, prefix="     "):
        """Add message to log display"""
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]

        # Apply decoding if enabled
        display_message = message
        if self.decode_mode and self.decoder:
            display_message = self.decoder.format_decoded_info(message)

        formatted = f"[{timestamp}] {prefix} {display_message}"

        # Add to display buffer
        self.display_buffer.append(formatted)

        # Print in log area if not paused or showing overlay
        if not self.paused and not self.show_help_overlay and not self.show_stats_overlay:
            print(ANSI.move_cursor(self.log_height, 1), end='')
            print(ANSI.CLEAR_LINE, end='')

            # Truncate if too long
            if len(formatted) > self.term_width:
                formatted = formatted[:self.term_width - 3] + "..."

            print(formatted, end='')
            print("\n", end='')  # This scrolls the log region

            # Restore cursor to input area
            self.draw_input_area()

    def update_stats(self, message):
        """Update statistics from message"""
        self.stats['total_messages'] += 1

        if self.patterns['duplicate'].search(message):
            self.stats['duplicates'] += 1
        if self.patterns['decode_fail'].search(message):
            self.stats['decode_failures'] += 1
        if self.patterns['bit_error'].search(message):
            self.stats['bit_errors'] += 1
        if self.patterns['mqtt'].search(message):
            self.stats['mqtt_messages'] += 1

        for match in self.patterns['icao'].finditer(message):
            self.stats['icao_addresses'].add(match.group(1).lower())

    def should_display(self, message):
        """Check if message passes filters"""
        if self.debug_mode:
            return True
        if not self.filters:
            return True

        for f in self.filters:
            if f.lower() in message.lower():
                self.stats['filtered_messages'] += 1
                return True
        return False

    def get_message_prefix(self, message):
        """Get prefix for message type"""
        if self.patterns['error'].search(message):
            return "\033[31m[ERR]\033[0m"
        elif self.patterns['warning'].search(message):
            return "\033[33m[WRN]\033[0m"
        elif self.patterns['mqtt'].search(message):
            return "\033[36m[MQT]\033[0m"
        elif self.patterns['info'].search(message):
            return "\033[34m[INF]\033[0m"
        else:
            return "     "

    def get_tab_suggestions(self, input_text):
        """Get suggestions for tab completion based on input"""
        suggestions = []

        # Parse current input
        if input_text.startswith('/rf '):
            # Suggest active filters for removal
            prefix = input_text[4:].strip()
            for f in self.filters:
                if not prefix or f.lower().startswith(prefix.lower()):
                    suggestions.append(f"/rf {f}")

        elif input_text.startswith('/f '):
            # Suggest common patterns and recent ICAOs
            prefix = input_text[3:].strip()

            # Common patterns
            common = ['MQTT', 'mqtt', 'Feed', 'feed', 'ERROR', 'WARNING', 'INFO',
                     'Failed', 'Skipped', 'duplicate', 'decode', 'Aircraft', 'protocol']
            for p in common:
                if not prefix or p.lower().startswith(prefix.lower()):
                    suggestions.append(f"/f {p}")

            # Recent ICAO addresses
            if self.stats['icao_addresses']:
                recent_icaos = list(self.stats['icao_addresses'])[-10:]  # Last 10
                for icao in recent_icaos:
                    if not prefix or icao.startswith(prefix.lower()):
                        suggestions.append(f"/f icao=0x{icao}")

        elif input_text.upper().startswith('AT+'):
            # AT command suggestions
            prefix = input_text[3:].upper()
            at_commands = [
                'FEED?', 'FEEDPROTOCOL?', 'FEEDPROTOCOL=0,MQTT', 'FEEDEN?', 'FEEDEN=0,1',
                'FEED=0,mqtt://broker.hivemq.com,1883,1,MQTT',
                'FEED=0,mqtt://test.mosquitto.org,1883,1,MQTT',
                'MQTTFMT?', 'MQTTFMT=0,JSON', 'MQTTFMT=0,BINARY',
                'LOG_LEVEL?', 'LOG_LEVEL=INFO', 'LOG_LEVEL=WARNINGS', 'LOG_LEVEL=ERRORS',
                'NETWORK_INFO?', 'SETTINGS?', 'SETTINGS=SAVE', 'REBOOT', 'RX_ENABLE?'
            ]
            for cmd in at_commands:
                if not prefix or cmd.startswith(prefix):
                    suggestions.append(f"AT+{cmd}")

        elif input_text.startswith('/'):
            # Command suggestions
            commands = [('/f ', 'Add filter'), ('/rf ', 'Remove filter'),
                       ('/lf', 'List filters'), ('/cf', 'Clear filters')]
            for cmd, desc in commands:
                if cmd.startswith(input_text):
                    suggestions.append(cmd)

        elif input_text == '':
            # Show common starting points
            suggestions = ['/f ', '/rf ', '/lf', '/cf', 'AT+']

        return suggestions

    def handle_tab_completion(self):
        """Handle Tab key for completion"""
        # Initialize tab completion if needed
        if self.tab_completion_index == -1:
            self.tab_suggestions = self.get_tab_suggestions(self.input_buffer)
            if not self.tab_suggestions:
                return  # No suggestions
            self.tab_completion_index = 0
        else:
            # Cycle to next suggestion
            self.tab_completion_index = (self.tab_completion_index + 1) % len(self.tab_suggestions)

        # Apply current suggestion
        if self.tab_suggestions:
            self.input_buffer = self.tab_suggestions[self.tab_completion_index]

            # Show hint if multiple suggestions
            if len(self.tab_suggestions) > 1:
                print(ANSI.move_cursor(self.log_height + 2, self.term_width - 20), end='')
                print(f"\033[90m[Tab: {self.tab_completion_index + 1}/{len(self.tab_suggestions)}]\033[0m", end='')

    def get_suggestions(self, text):
        """Get tab completion suggestions based on input"""
        suggestions = []

        # Empty input - show common commands
        if not text:
            return ['/f ', '/rf ', '/lf', '/cf', 'AT+'] + self.common_at_commands[:3]

        # Filter commands
        if text.startswith('/f '):
            # Suggest common patterns for adding filters
            prefix = text[3:]
            suggestions = [f'/f {p}' for p in self.common_patterns
                          if p.lower().startswith(prefix.lower())]
            # Also add recent ICAO addresses
            recent_icaos = list(self.stats['icao_addresses'])[-5:]
            for icao in recent_icaos:
                suggestions.append(f'/f icao=0x{icao}')

        elif text.startswith('/rf '):
            # Suggest existing filters for removal
            prefix = text[4:]
            suggestions = [f'/rf {f}' for f in self.filters
                          if f.lower().startswith(prefix.lower())]

        elif text.startswith('/'):
            # Suggest filter commands
            commands = ['/f ', '/rf ', '/lf', '/cf']
            suggestions = [c for c in commands if c.startswith(text)]

        # AT commands
        elif text.upper().startswith('AT'):
            # Suggest AT commands
            upper_text = text.upper()
            suggestions = [cmd for cmd in self.common_at_commands
                          if cmd.startswith(upper_text)]

            # Add dynamic suggestions based on context
            if upper_text.startswith('AT+FEED'):
                if 'PROTOCOL' in upper_text:
                    for i in range(10):
                        suggestions.append(f'AT+FEEDPROTOCOL={i},MQTT')
                        suggestions.append(f'AT+FEEDPROTOCOL?{i}')
                else:
                    for i in range(10):
                        suggestions.append(f'AT+FEED?{i}')
                        suggestions.append(f'AT+FEEDEN={i},1')
                        suggestions.append(f'AT+FEED={i},mqtt://broker.hivemq.com,1883,1,MQTT')
            elif upper_text.startswith('AT+MQTT'):
                for i in range(10):
                    suggestions.append(f'AT+MQTTFMT?{i}')
                    suggestions.append(f'AT+MQTTFMT={i},JSON')
                    suggestions.append(f'AT+MQTTFMT={i},BINARY')

        # Filter command history
        else:
            # Search command history
            suggestions = [cmd for cmd in self.command_history
                          if cmd.startswith(text) and cmd != text]

        return suggestions[:10]  # Limit to 10 suggestions

    def process_command(self, cmd):
        """Process user command"""
        if not cmd:
            return

        # Reset tab completion
        self.tab_suggestions = []
        self.tab_index = -1

        self.command_history.append(cmd)
        self.history_index = -1

        # Handle filter commands
        if cmd.startswith('/'):
            parts = cmd.split(maxsplit=1)
            command = parts[0].lower()

            if command == '/f':  # Add filter
                if len(parts) > 1:
                    self.filters.append(parts[1])
                    self.add_to_log(f"Filter added: {parts[1]}", "\033[35m[SYS]\033[0m")

            elif command == '/rf':  # Remove filter
                if len(parts) > 1 and parts[1] in self.filters:
                    self.filters.remove(parts[1])
                    self.add_to_log(f"Filter removed: {parts[1]}", "\033[35m[SYS]\033[0m")

            elif command == '/lf':  # List filters
                if self.filters:
                    self.add_to_log(f"Filters: {', '.join(self.filters)}", "\033[35m[SYS]\033[0m")
                else:
                    self.add_to_log("No filters active", "\033[35m[SYS]\033[0m")

            elif command == '/cf':  # Clear filters
                self.filters = []
                self.add_to_log("All filters cleared", "\033[35m[SYS]\033[0m")

            else:
                self.add_to_log(f"Unknown command: {command}", "\033[35m[SYS]\033[0m")

        else:
            # Send as AT command or raw
            if not cmd.endswith('\r\n'):
                cmd += '\r\n'

            if self.ws.send_text(cmd):
                self.add_to_log(f"Sent: {cmd.strip()}", "\033[32m[TX]\033[0m")
                self.stats['commands_sent'] += 1

        # Redraw status line with updated filter count
        self.draw_separator()

    def receive_thread(self):
        """Thread for receiving WebSocket messages"""
        last_keepalive = time.time()

        while self.running and self.ws.connected:
            msg = self.ws.receive(timeout=0.1)

            if msg is None:
                self.add_to_log("Connection closed by server", "\033[31m[ERR]\033[0m")
                break
            elif msg:
                for line in msg.split('\n'):
                    line = line.strip('\r\n')
                    if line:
                        self.update_stats(line)
                        self.buffer.append(line)

                        if self.log_handle:
                            self.log_handle.write(f"{datetime.now()}: {line}\n")
                            self.log_handle.flush()

                        if self.should_display(line):
                            prefix = self.get_message_prefix(line)
                            self.add_to_log(line, prefix)

            # Keepalive - don't send anything, connection should stay alive
            # The ADSBee console doesn't need keepalives
            if time.time() - last_keepalive > 30:
                # Only reset timer, don't send anything
                # This avoids "Can't parse 0 length command" errors
                last_keepalive = time.time()

    def input_thread(self):
        """Handle keyboard input"""
        while self.running:
            try:
                char = sys.stdin.read(1)
                if not char:
                    time.sleep(0.01)
                    continue

                # Handle special keys
                if ord(char) == 13:  # Enter
                    self.process_command(self.input_buffer)
                    self.input_buffer = ""

                elif ord(char) == 127 or ord(char) == 8:  # Backspace
                    if self.input_buffer:
                        self.input_buffer = self.input_buffer[:-1]
                        # Reset tab completion
                        self.tab_suggestions = []
                        self.tab_index = -1

                elif ord(char) == 3:  # Ctrl+C
                    self.running = False
                    break

                elif ord(char) == 12:  # Ctrl+L - Clear screen
                    self.display_buffer.clear()
                    print(ANSI.move_cursor(1, 1), end='')
                    for i in range(self.log_height):
                        print(ANSI.CLEAR_LINE, end='')
                        if i < self.log_height - 1:
                            print("\n", end='')

                elif ord(char) == 16:  # Ctrl+P - Pause
                    self.paused = not self.paused
                    self.draw_separator()

                elif ord(char) == 4:  # Ctrl+D - Debug mode
                    self.debug_mode = not self.debug_mode
                    self.draw_separator()

                elif ord(char) == 24:  # Ctrl+X - Toggle decoding
                    if self.decoder:
                        self.decode_mode = not self.decode_mode
                        mode = "enabled" if self.decode_mode else "disabled"
                        self.add_to_log(f"Hex decoding {mode}", "\033[35m[SYS]\033[0m")
                        self.draw_separator()

                elif ord(char) == 27:  # ESC sequence
                    next1 = sys.stdin.read(1)
                    if next1 == 'O':  # Function keys
                        next2 = sys.stdin.read(1)
                        if next2 == 'P':  # F1
                            self.show_help_overlay = not self.show_help_overlay
                            if self.show_help_overlay:
                                self.show_help()
                            else:
                                self.setup_terminal()
                        elif next2 == 'Q':  # F2
                            self.show_stats_overlay = not self.show_stats_overlay
                            if self.show_stats_overlay:
                                self.show_statistics()
                            else:
                                self.setup_terminal()
                    elif next1 == '[':  # Arrow keys
                        next2 = sys.stdin.read(1)
                        if next2 == 'A':  # Up arrow
                            if self.command_history and self.history_index < len(self.command_history) - 1:
                                self.history_index += 1
                                self.input_buffer = self.command_history[-(self.history_index + 1)]
                        elif next2 == 'B':  # Down arrow
                            if self.history_index > -1:
                                self.history_index -= 1
                                if self.history_index == -1:
                                    self.input_buffer = ""
                                else:
                                    self.input_buffer = self.command_history[-(self.history_index + 1)]

                elif ord(char) == 9:  # Tab key
                    self.handle_tab_completion()

                elif ord(char) == 9:  # Tab key
                    self.handle_tab_completion()

                elif char == '?' and len(self.input_buffer) == 0:
                    # Only show help if ? is pressed on empty line
                    self.show_help_overlay = not self.show_help_overlay
                    if self.show_help_overlay:
                        self.show_help()
                    else:
                        self.setup_terminal()

                elif 32 <= ord(char) < 127:  # Printable character (including ?)
                    self.input_buffer += char
                    # Reset tab completion on new input
                    self.tab_completion_index = -1
                    self.tab_suggestions = []
                    # Reset tab completion when typing
                    self.tab_suggestions = []
                    self.tab_index = -1

                self.draw_input_area()

            except:
                time.sleep(0.01)

    def run(self):
        """Main monitor loop"""
        try:
            # Connect to WebSocket
            self.ws.connect()

            # Setup terminal
            self.setup_terminal()

            # Set log level if requested
            if hasattr(self, 'initial_log_level') and self.initial_log_level:
                self.ws.send_text(f"AT+LOG_LEVEL={self.initial_log_level}\r\n")
                self.add_to_log(f"Setting log level to {self.initial_log_level}", "\033[32m[SYS]\033[0m")

            # Initial messages
            self.add_to_log(f"Connected to ws://{self.host}/console", "\033[32m[SYS]\033[0m")
            self.add_to_log("Press F1 for help | Check log level: AT+LOG_LEVEL?", "\033[35m[SYS]\033[0m")
            self.add_to_log("Tip: AT+LOG_LEVEL=INFO (verbose) or =WARNINGS (normal)", "\033[35m[TIP]\033[0m")

            # Start receive thread
            recv_thread = threading.Thread(target=self.receive_thread)
            recv_thread.daemon = True
            recv_thread.start()

            # Handle input in main thread
            self.input_thread()

        except Exception as e:
            print(f"\nError: {e}")
        finally:
            self.restore_terminal()

            if self.log_handle:
                self.log_handle.close()

            self.ws.close()

            # Print final stats
            print("\nSession ended")
            print(f"Total messages: {self.stats['total_messages']:,}")
            print(f"MQTT messages: {self.stats['mqtt_messages']:,}")


def main():
    parser = argparse.ArgumentParser(description='ADSBee Clean Monitor')
    parser.add_argument('--host', default='192.168.1.73', help='ADSBee IP address')
    parser.add_argument('--filter', '-f', action='append', help='Initial filter patterns')
    parser.add_argument('--log', '-l', help='Log output to file')
    parser.add_argument('--mqtt', action='store_true', help='Filter MQTT messages only')
    parser.add_argument('--log-level', choices=['INFO', 'WARNINGS', 'ERRORS', 'SILENT'],
                        help='Set ADSBee log level on connect (optional)')

    args = parser.parse_args()

    # Build filter list
    filters = args.filter or []
    if args.mqtt:
        filters.extend(['MQTT', 'mqtt', 'Feed', 'feed', 'protocol'])

    # Create and run monitor
    monitor = CleanMonitor(args.host, filters, args.log)

    # Set log level if specified
    if args.log_level:
        monitor.initial_log_level = args.log_level
    else:
        monitor.initial_log_level = None

    monitor.run()


if __name__ == "__main__":
    main()
