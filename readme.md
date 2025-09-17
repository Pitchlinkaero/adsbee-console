# ADSBee Console Monitor

A Python WebSocket console for debugging the ADSBee ADS-B receiver console.

## Features

- **Tab completion** - Press Tab to complete commands and filters
- **Hex value decoding** - Automatic decoding of ICAO addresses and message types
- **Overlay help** - F1 shows help without cluttering logs
- **? character support** - Use ? in AT commands (e.g., AT+FEED?)
- **Smart log level control** - Doesn't force log level changes
- **Color-coded messages** - Easy identification of message types
- **Statistics overlay** - F2 shows stats without interrupting logs
- **Command history** - Use ↑/↓ arrows to navigate previous commands
- **Real-time filtering** - Filter messages by pattern or type
- **Session logging** - Save output to file for later analysis

## Quick Start

```bash
# Basic usage - respects current log level
python adsbee_console.py

# Debug MQTT issues with verbose logging
python adsbee_console.py --log-level INFO --mqtt

# Track specific aircraft
python adsbee_console.py -f "icao=0xaa7f03"

# Log session to file
python adsbee_console.py --log session.log
```

## Command Line Options

```bash
python adsbee_console.py [OPTIONS]

Options:
  --host HOST           ADSBee IP address (default: 192.168.4.1)
  --port PORT           WebSocket port (default: 80)
  --log-level LEVEL     Set log level: SILENT, ERRORS, WARNINGS, INFO
  --log FILE            Save output to file
  --mqtt                Filter MQTT messages only
  --errors              Filter errors only
  -f PATTERN            Add filter pattern
  -c COMMAND            Send command on connect
  --help                Show help message
```

## Interactive Commands

| Key/Command | Description | Example |
|------------|-------------|------|
| `F1` | Toggle help overlay | Shows commands without cluttering log |
| `F2` | Toggle statistics overlay | Shows stats without interrupting |
| `Tab` | Auto-complete | Complete commands and filters |
| `↑/↓` | Command history | Navigate previous commands |
| `Ctrl+C` | Exit console | Clean shutdown |
| `Ctrl+L` | Clear screen | Clear log area |
| `Ctrl+P` | Pause/resume output | Pause scrolling |
| `Ctrl+D` | Toggle debug mode | Bypass all filters |
| `Ctrl+X` | Toggle hex decoding | Enable/disable inline decoding |
| `/f <pattern>` | Add filter | `/f MQTT`, `/f ERROR` |
| `/rf <pattern>` | Remove specific filter | `/rf MQTT` |
| `/lf` | List active filters | Shows all current filters |
| `/cf` | Clear all filters | Remove all filters |
| `AT+<command>` | Direct AT command | `AT+FEED?`, `AT+LOG_LEVEL=INFO` |
| `?` | Query in commands | `AT+FEED?` works correctly |


## Tab Completion

The console includes intelligent Tab completion:

### Filter Commands:
- Type `/f ` + Tab → Suggests common patterns and recent ICAO addresses
- Type `/rf ` + Tab → Lists your active filters for removal
- Type `/` + Tab → Shows all filter commands

### AT Commands:
- Type `AT+` + Tab → Common AT commands
- Type `AT+FEED` + Tab → Feed-specific commands
- Type `AT+LOG` + Tab → Log level commands

### Examples:
```bash
/f M[Tab]           → /f MQTT
/rf [Tab]           → cycles through active filters
AT+FE[Tab]          → AT+FEED?
AT+FEEDPRO[Tab]     → AT+FEEDPROTOCOL?
```

## Log Level Control

### Default Behavior:
- **Check current level**: `AT+LOG_LEVEL?`
- **Change manually**: `AT+LOG_LEVEL=INFO` or `=WARNINGS`

### Optional Override:
```bash
# Set log level on connect (optional)
python adsbee_console.py --log-level INFO      # Maximum detail
python adsbee_console.py --log-level WARNINGS  # Normal operation
python adsbee_console.py --log-level ERRORS    # Errors only
python adsbee_console.py --log-level SILENT    # No logs
```

## Installation

### Requirements

```bash
# Make script executable
chmod +x adsbee_console.py

# Optional Dependencies
pip install requirements.txt -r

# Run directly
./adsbee_console.py
```

### Python Version
- Python 3.6 or higher required
- Tested with Python 3.10

## Hex Value Decoding

The console can decode hex values inline to make debugging easier. Toggle with **Ctrl+X**.

### Downlink Format (DF) Codes:
| DF | Description | Shows As |
|----|-------------|----------|
| 00 | Short air-air surveillance | [Short ACAS] |
| 04-05 | Surveillance altitude/identity | [Surv. altitude/identity] |
| 11 | All-call reply | [All-call] |
| 17 | Extended squitter (ADS-B) | [ADS-B] |
| 18 | Extended squitter/non-transponder | [Extended squitter] |
| 19 | Military extended squitter | [Military extended squitter] |
| 20-21 | Comm-B altitude/identity | [Comm-B] |

### ADS-B Message Type Codes (for DF=17/18):
| Type | Description |
|------|-------------|
| 1-4 | Aircraft identification (callsign) |
| 5-8 | Surface position |
| 9-18 | Airborne position (w/ Baro Alt) |
| 19 | Airborne velocity |
| 20-22 | Airborne position (w/ GNSS Alt) |
| 28 | Extended squitter AC status |
| 29 | Target state and status |
| 31 | Aircraft operation status |

### ICAO Country Codes:
The first characters of ICAO addresses indicate country:
- **A** - USA (e.g., 0xAA7F03)
- **C** - Canada (e.g., 0xC84095)
- **7C** - Australia
- **40** - UK
- **3C** - Germany
- **38-3F** - France/Italy/Spain
- **48** - Netherlands
- **4B** - Switzerland

## Message Types and Color Coding

The console use color coding to help identify message types:

| Color/Tag | Meaning | Example |
|-----------|---------|---------|
| 🔴 `[ERR]` | Errors | Failed operations, connection errors |
| 🟡 `[WRN]` | Warnings | Skipped packets, minor issues |
| 🔵 `[INF]` | Info | General information messages |
| 🟢 `[TX]` | Transmitted | Commands sent to device |
| 🔷 `[MQT]` | MQTT | MQTT-related messages |
| 🟣 `[SYS]` | System | console system messages |

## Decoding Examples

Without decoding:
```
[NOFIX] df=17 icao=0xaa7f03 0x8DAA7F039901BD9C60048031C463
[INVLD] df=11 icao=0x231911 0x5B231911F82335AAC42146E2E59C
Failed to apply ADSB message with typecode 29 to ICAO 0xaa7f03
```

With decoding enabled (Ctrl+X):
```
[NOFIX] df=17 [ADS-B] icao=0xaa7f03 [USA] 0x8DAA7F039901BD9C60048031C463
[INVLD] df=11 [All-call] icao=0x231911 [Various EU] 0x5B231911F82335AAC42146E2E59C
Failed to apply ADSB message with typecode 29 [Target state and status] to ICAO 0xaa7f03 [USA]
```

## Question Mark (?) Support

- **Empty prompt + ?** → Shows help overlay
- **In commands** → Works as query character
- **Examples**:
  - `AT+FEED?` - Query all feeds
  - `AT+FEEDPROTOCOL?` - Show all protocols
  - `AT+LOG_LEVEL?` - Check current log level

## Common AT Commands

Here are useful AT commands for debugging:

```bash
# Query Commands (? now works!)
AT+FEED?              # List all feed configurations
AT+FEED?0             # Query specific feed
AT+FEEDPROTOCOL?      # Show all feed protocols
AT+FEEDPROTOCOL?0     # Query specific feed protocol
AT+FEEDEN?            # Show enabled feeds
AT+LOG_LEVEL?         # Current log level
AT+NETWORK_INFO?      # Network status
AT+SETTINGS?          # View all settings

# Configuration Commands
AT+LOG_LEVEL=INFO     # Set log level (SILENT/ERRORS/WARNINGS/INFO)
AT+FEEDPROTOCOL=0,MQTT  # Set feed 0 to MQTT protocol
AT+FEED=0,broker.hivemq.com,1883  # Configure MQTT broker
AT+FEEDEN=0,1         # Enable feed 0

# Control Commands
AT+REBOOT             # Reboot device
AT+SETTINGS=SAVE      # Save settings
AT+RX_ENABLE=1,1      # Enable receivers
```

## Statistics Tracker

The monitors track various statistics:

- **Total messages** - All messages received
- **Filtered messages** - Messages matching filters
- **Commands sent** - AT commands sent
- **Duplicate packets** - ADS-B duplicate detections
- **Decode failures** - Position decode errors
- **Bit errors corrected** - Single-bit error corrections
- **MQTT messages** - MQTT-related activity
- **Unique aircraft** - Unique ICAO addresses seen


## Log File Format

When using `--log` option, messages are saved with timestamps:

```
================================================================================
Session started: 2025-01-16 14:30:00
Host: 192.168.1.73
================================================================================
[14:30:01.123] [INF] Connected to device
[14:30:02.456] [MQT] MQTT: Connecting to broker
[14:30:03.789] [ERR] Failed to apply ADSB message
```

## Best Practices

1. **Set log level to INFO** for debugging MQTT issues
2. **Use filters** to reduce noise when looking for specific issues
3. **Log to file** for long debugging sessions
4. **console statistics** (F2) to identify patterns
5. **Use Tab completion** for faster command entry
6. **Keep the console running** to catch intermittent issues

## Usage Examples

### Debug MQTT Integration
```bash
python adsbee_console.py --mqtt --log-level INFO --log mqtt_debug.log

# In console:
AT+FEED?           # Check feed configuration (use Tab!)
AT+FEEDPROTOCOL?   # Check protocol settings
F2                 # Show statistics overlay
Ctrl+X             # Enable hex decoding
```

### Track Specific Aircraft
```bash
python adsbee_console.py -f "icao=0xaa7f03"
# With decoding enabled: icao=0xaa7f03 [USA]
```

### Monitor Errors Only
```bash
python adsbee_console.py --errors --log-level ERRORS
```

### Full Debug Session
```bash
python adsbee_console.py --log-level INFO --log full_debug.log
```

## Troubleshooting

### No Output Visible
1. Check log level: `AT+LOG_LEVEL?`
2. Set to INFO: `AT+LOG_LEVEL=INFO`
3. Clear filters: `/cf`
4. Toggle debug mode: `Ctrl+D`

## License

This monitoring tool is provided as-is for debugging ADSBee devices under GNU 3.0.
