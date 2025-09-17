#!/usr/bin/env python3
"""
ADS-B Decoder Module for ADSBee Monitor
Decodes ICAO addresses, message types, and other hex values
"""

class ADSBDecoder:
    """Decoder for ADS-B hex values and message types"""

    def __init__(self):
        # Downlink Format (DF) descriptions
        self.df_formats = {
            '0': 'Short air-air surveillance (ACAS)',
            '00': 'Short air-air surveillance (ACAS)',
            '1': 'Reserved',
            '01': 'Reserved',
            '2': 'Reserved',
            '02': 'Reserved',
            '3': 'Reserved',
            '03': 'Reserved',
            '4': 'Surveillance altitude reply',
            '04': 'Surveillance altitude reply',
            '5': 'Surveillance identity reply',
            '05': 'Surveillance identity reply',
            '6': 'Reserved',
            '06': 'Reserved',
            '7': 'Reserved',
            '07': 'Reserved',
            '8': 'Reserved',
            '08': 'Reserved',
            '9': 'Reserved',
            '09': 'Reserved',
            '10': 'Reserved',
            '11': 'All-call reply',
            '12': 'Reserved',
            '13': 'Reserved',
            '14': 'Reserved',
            '15': 'Reserved',
            '16': 'Long air-air surveillance (ACAS)',
            '17': 'Extended squitter (ADS-B)',
            '18': 'Extended squitter/non-transponder',
            '19': 'Military extended squitter',
            '20': 'Comm-B altitude reply',
            '21': 'Comm-B identity reply',
            '22': 'Reserved',
            '23': 'Reserved',
            '24': 'Comm-D (ELM)',
            '25': 'Reserved',
            '26': 'Reserved',
            '27': 'Reserved',
            '28': 'Reserved',
            '29': 'Reserved',
            '30': 'Reserved',
            '31': 'Reserved'
        }

        # Message validation status meanings
        self.status_meanings = {
            'VALID': 'Valid checksum',
            'INVLD': 'Invalid checksum',
            'NOFIX': 'No position fix',
            'FIXED': 'Position fixed',
            'ERROR': 'Decode error'
        }
        # Common US aircraft ICAO prefixes (partial list)
        self.icao_country_prefixes = {
            'A': 'USA',
            'C': 'Canada',
            '4': 'Mexico',
            'E': 'Venezuela/Argentina',
            '0': 'Various',
            '7': 'Australia',
            '8': 'Japan/Korea',
            '3': 'France/Italy/Spain',
            '2': 'Various EU',
        }

        # ADS-B message type codes (DF17/18 Type Codes)
        self.message_types = {
            '0': 'No position information',
            '1': 'Aircraft identification (callsign)',
            '2': 'Aircraft identification (callsign)',
            '3': 'Aircraft identification (callsign)',
            '4': 'Aircraft identification (callsign)',
            '5': 'Surface position',
            '6': 'Surface position',
            '7': 'Surface position',
            '8': 'Surface position',
            '9': 'Airborne position (w/ Baro Alt)',
            '10': 'Airborne position (w/ Baro Alt)',
            '11': 'Airborne position (w/ Baro Alt)',
            '12': 'Airborne position (w/ Baro Alt)',
            '13': 'Airborne position (w/ Baro Alt)',
            '14': 'Airborne position (w/ Baro Alt)',
            '15': 'Airborne position (w/ Baro Alt)',
            '16': 'Airborne position (w/ Baro Alt)',
            '17': 'Airborne position (w/ Baro Alt)',
            '18': 'Airborne position (w/ Baro Alt)',
            '19': 'Airborne velocity',
            '20': 'Airborne position (w/ GNSS Alt)',
            '21': 'Airborne position (w/ GNSS Alt)',
            '22': 'Airborne position (w/ GNSS Alt)',
            '23': 'Test message',
            '24': 'Surface system status',
            '25': 'Reserved',
            '26': 'Reserved',
            '27': 'Reserved',
            '28': 'Extended squitter AC status',
            '29': 'Target state and status',
            '30': 'Reserved',
            '31': 'Aircraft operation status',
        }

        # Common airline ICAO prefixes for callsign interpretation
        self.airline_prefixes = {
            'AAL': 'American',
            'UAL': 'United',
            'DAL': 'Delta',
            'SWA': 'Southwest',
            'JBU': 'JetBlue',
            'SKW': 'SkyWest',
            'ASA': 'Alaska',
            'FFT': 'Frontier',
            'NKS': 'Spirit',
            'VRD': 'Virgin America',
            'BAW': 'British Airways',
            'DLH': 'Lufthansa',
            'AFR': 'Air France',
            'KLM': 'KLM',
            'RYR': 'Ryanair',
        }

        # Cache for decoded values to avoid repeated calculations
        self.cache = {}

    def decode_icao(self, icao_hex):
        """
        Decode ICAO hex address to country and possible info
        Args:
            icao_hex: String hex ICAO like 'aa7f03' or '0xaa7f03'
        Returns:
            Dictionary with decoded information
        """
        # Clean the input
        icao_hex = icao_hex.lower().replace('0x', '').strip()

        # Check cache
        if icao_hex in self.cache:
            return self.cache[icao_hex]

        result = {
            'hex': icao_hex,
            'country': 'Unknown',
            'military': False,
            'special': None
        }

        # Decode by prefix
        if icao_hex:
            first_char = icao_hex[0].upper()

            # US aircraft (A-series)
            if first_char == 'A':
                result['country'] = 'USA'
                # Check for special ranges
                if icao_hex.startswith('adf'):
                    result['military'] = True
                    result['special'] = 'US Military'

            # Other countries
            elif first_char in self.icao_country_prefixes:
                result['country'] = self.icao_country_prefixes[first_char]

            # Check for special patterns
            if icao_hex.startswith('7c'):
                result['country'] = 'Australia'
            elif icao_hex.startswith('c0'):
                result['country'] = 'Canada'
            elif icao_hex.startswith('a0'):
                result['country'] = 'USA'
            elif icao_hex.startswith('4b'):
                result['country'] = 'Switzerland'
            elif icao_hex.startswith('40'):
                result['country'] = 'UK'
            elif icao_hex.startswith('3c'):
                result['country'] = 'Germany'
            elif icao_hex.startswith('38'):
                result['country'] = 'France'
            elif icao_hex.startswith('48'):
                result['country'] = 'Netherlands'

        # Cache the result
        self.cache[icao_hex] = result
        return result

    def decode_message_type(self, type_code):
        """
        Decode ADS-B message type code
        Args:
            type_code: Integer or string type code (0-31)
        Returns:
            String description of message type
        """
        type_str = str(type_code)
        return self.message_types.get(type_str, f'Unknown type {type_code}')

    def decode_df(self, df_code):
        """
        Decode Downlink Format (DF) code
        Args:
            df_code: Integer or string DF code (0-31)
        Returns:
            String description of DF format
        """
        df_str = str(df_code).zfill(2) if int(df_code) < 10 else str(df_code)
        # Try both with and without leading zero
        result = self.df_formats.get(df_str)
        if not result:
            result = self.df_formats.get(str(int(df_code)))
        return result if result else f'Unknown DF {df_code}'

    def decode_altitude(self, alt_code):
        """
        Decode altitude from hex or integer code
        Args:
            alt_code: Altitude code (hex string or integer)
        Returns:
            Altitude in feet
        """
        if isinstance(alt_code, str):
            # Convert hex to int if needed
            if alt_code.startswith('0x'):
                alt_code = int(alt_code, 16)
            elif alt_code.isdigit():
                alt_code = int(alt_code)
            else:
                try:
                    alt_code = int(alt_code, 16)
                except:
                    return None

        # Standard altitude decoding (25ft increments)
        if alt_code > 0:
            return alt_code * 25 - 1000
        return 0

    def decode_callsign(self, callsign):
        """
        Decode airline callsign to airline name
        Args:
            callsign: String callsign like 'AAL123'
        Returns:
            Dictionary with airline info
        """
        if not callsign:
            return None

        callsign = callsign.strip().upper()

        # Check airline prefixes
        for prefix, airline in self.airline_prefixes.items():
            if callsign.startswith(prefix):
                return {
                    'callsign': callsign,
                    'airline': airline,
                    'flight': callsign[len(prefix):]
                }

        return {
            'callsign': callsign,
            'airline': None,
            'flight': None
        }

    def format_decoded_info(self, text, decode_inline=True):
        """
        Find and decode hex values in text, adding decoded info
        Args:
            text: Input text with hex values
            decode_inline: If True, add decoded info inline
        Returns:
            Text with decoded information added
        """
        import re

        # Pattern for ICAO addresses
        icao_pattern = r'icao[=:]\s*0x([a-fA-F0-9]{6})'

        # Pattern for message type codes
        type_pattern = r'typecode\s+(\d+)'

        # Pattern for altitude
        alt_pattern = r'altitude[=:]\s*0x([a-fA-F0-9]+)'

        # Pattern for DF (Downlink Format)
        df_pattern = r'df[=:]?(\d{1,2})\b'

        result = text

        if decode_inline:
            # Decode ICAO addresses
            for match in re.finditer(icao_pattern, text, re.I):
                icao_hex = match.group(1)
                info = self.decode_icao(icao_hex)
                if info['country'] != 'Unknown':
                    decoded = f" [{info['country']}"
                    if info['military']:
                        decoded += " MIL"
                    if info['special']:
                        decoded += f" {info['special']}"
                    decoded += "]"

                    # Insert after the ICAO
                    insert_pos = match.end()
                    result = result[:insert_pos] + decoded + result[insert_pos:]

            # Decode message types
            for match in re.finditer(type_pattern, text, re.I):
                type_code = match.group(1)
                decoded_type = self.decode_message_type(type_code)
                if 'Unknown' not in decoded_type:
                    decoded = f" [{decoded_type}]"
                    insert_pos = match.end()
                    result = result[:insert_pos] + decoded + result[insert_pos:]

            # Decode DF (Downlink Format)
            df_matches = list(re.finditer(df_pattern, text, re.I))
            # Process in reverse to maintain positions
            for match in reversed(df_matches):
                df_code = match.group(1)
                decoded_df = self.decode_df(df_code)
                # Only add if it's a known format and not too long
                if 'Unknown' not in decoded_df and len(decoded_df) < 40:
                    # Shorten some common ones
                    if 'Extended squitter' in decoded_df:
                        decoded_df = 'ADS-B'
                    elif 'Short air-air' in decoded_df:
                        decoded_df = 'Short ACAS'
                    elif 'All-call reply' in decoded_df:
                        decoded_df = 'All-call'
                    elif 'Surveillance' in decoded_df:
                        decoded_df = decoded_df.replace('Surveillance ', 'Surv.')

                    decoded = f" [{decoded_df}]"
                    insert_pos = match.end()
                    result = result[:insert_pos] + decoded + result[insert_pos:]

        return result

    def get_summary(self, icao_addresses):
        """
        Get summary of ICAO addresses by country
        Args:
            icao_addresses: Set or list of ICAO hex addresses
        Returns:
            Dictionary with country counts
        """
        countries = {}
        military_count = 0

        for icao in icao_addresses:
            info = self.decode_icao(icao)
            country = info['country']

            if country not in countries:
                countries[country] = 0
            countries[country] += 1

            if info['military']:
                military_count += 1

        return {
            'countries': countries,
            'military': military_count,
            'total': len(icao_addresses)
        }


# Quick test if run directly
if __name__ == "__main__":
    decoder = ADSBDecoder()

    # Test ICAO decoding
    test_icaos = ['aa7f03', 'adf7c2', 'c00123', '7c4321', '400000']
    for icao in test_icaos:
        info = decoder.decode_icao(icao)
        print(f"ICAO {icao}: {info}")

    # Test message type decoding
    for i in [1, 9, 19, 28, 29]:
        print(f"Type {i}: {decoder.decode_message_type(i)}")

    # Test inline decoding
    test_texts = [
        "Failed to apply ADSB message with typecode 29 to ICAO 0xaa7f03",
        "[NOFIX] df=17 icao=0xaa7f03 0x8DAA7F039901BD9C60048031C463",
        "[INVLD] df=11 icao=0x231911 0x5B231911F82335AAC42146E2E59C"
    ]

    for test_text in test_texts:
        decoded = decoder.format_decoded_info(test_text)
        print(f"\nOriginal: {test_text}")
        print(f"Decoded:  {decoded}")
