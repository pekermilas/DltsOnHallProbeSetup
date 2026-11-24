# -*- coding: utf-8 -*-
"""
HDS-4 Hall/DLTS selector (hardware/hallDltsSelector/): the planned relay box
that replaces the four manual A/B boxes between the Instec stage contacts
P1-P4 and the instruments.

Built and driven the same way as the Hall software's switch box
(HallProbe_Software/switchBox.py): an Arduino running the stock
**StandardFirmata** sketch, with all the logic here in Python through
pyfirmata2. A table maps a mode to pin levels (set_pins), and set_state()
writes them with arduino.digital[pin].write().

    position A = Hall  (Keithley 2450 through the Arduino switch box)
                 - also every contact's state with no relay power / at boot
    position B = DLTS  (MFIA: P1 HCUR, P2 LCUR, P3 LPOT, P4 free)

Each contact is a changeover relay pair (centre + guard), so Hall and DLTS are
never connected together.

Difference from switchBox.py, for the Hall + DLTS merge: the board handle and
the connection flag live on the object (self.board, self.connected), not in an
app config module, so both programs can import this file.

Example:
    import hallDltsSelector_Control as hdsC
    hdsC.connect_arduino('COM8')
    hdsC.set_mode('dlts')
    hdsC.get_state()          # {'P1': 'B', 'P2': 'B', 'P3': 'B', 'P4': 'B'}
    hdsC.disconn_arduino()
"""

from pyfirmata2 import Arduino


class HallDltsSelector:
    # Arduino digital pin that drives each contact's relay pair (centre + guard).
    CONTROL_PINS = {'P1': 2, 'P2': 3, 'P3': 4, 'P4': 5}
    # Front-panel LEDs: lit when some contact is on that side.
    LED_PINS = {'hall': 10, 'dlts': 11}
    # Analog input reading the switched relay-coil supply through a 10k/10k divider.
    POWER_SENSE_PIN = 0          # A0
    POWER_ON_LEVEL = 0.4         # fraction of 5 V at A0 (about 2 V)
    # StandardFirmata drives every pin LOW at boot, so the relay module must
    # energize on HIGH ("high-level trigger"): LOW = released = Hall.
    RELAY_ON_LEVEL = 1
    POSITION_NAMES = {'A': 'Hall', 'B': 'DLTS'}
    # What each DLTS-side (B) jack is cabled to on the MFIA (2-terminal setup).
    DLTS_CABLING = {'P1': 'MFIA Signal Output HCUR', 'P2': 'MFIA Signal Input LCUR',
                    'P3': 'MFIA Signal Input LPOT', 'P4': 'free'}

    def __init__(self, boardFactory=Arduino):
        self.boardFactory = boardFactory     # tests pass a fake board class
        self.board = None
        self.connected = False
        self.port = None
        # Last levels written (Firmata cannot read them back); boot state = Hall.
        self.positions = dict.fromkeys(self.CONTROL_PINS, 'A')
        self.powerLevel = None               # latest A0 sample, 0-1 (None until one arrives)

    # ---- mode table -----------------------------------------------------------
    def configurations(self, mode):
        """Position of each contact for `mode` ('hall' or 'dlts')."""
        mode = str(mode).lower()
        if mode == 'hall':
            P = {'P1': 'A', 'P2': 'A', 'P3': 'A', 'P4': 'A'}
        elif mode == 'dlts':
            P = {'P1': 'B', 'P2': 'B', 'P3': 'B', 'P4': 'B'}
        else:
            raise ValueError("Unsupported selector mode (use 'hall' or 'dlts')")
        return P

    def set_pins(self, P):
        """Pin levels for positions P ({'P1': 'A'|'B', ...}; contacts left out keep
        their current position). Returns (pinsDict {pin: level}, pinMap {contact: position})."""
        pinMap = dict(self.positions)
        for contact, pos in P.items():
            contact, pos = str(contact).upper(), str(pos).upper()
            if contact not in self.CONTROL_PINS:
                raise ValueError(f"Unknown contact {contact!r} (use P1-P4)")
            if pos not in self.POSITION_NAMES:
                raise ValueError(f"Unknown position {pos!r} (use 'A' = Hall or 'B' = DLTS)")
            pinMap[contact] = pos
        off = 1 - self.RELAY_ON_LEVEL
        pinsDict = {self.CONTROL_PINS[c]: (self.RELAY_ON_LEVEL if p == 'B' else off)
                    for c, p in pinMap.items()}
        return pinsDict, pinMap

    def set_state(self, pinsDict, pinMap=None):
        """Write the pin levels to the board (and the front LEDs)."""
        if not self.connected or self.board is None:
            raise RuntimeError("Hall/DLTS selector is not connected")
        for pin, level in pinsDict.items():
            self.board.digital[pin].write(level)
        if pinMap is not None:
            self.positions = dict(pinMap)
        self.board.digital[self.LED_PINS['hall']].write(int('A' in self.positions.values()))
        self.board.digital[self.LED_PINS['dlts']].write(int('B' in self.positions.values()))
        return 0

    # ---- connection -------------------------------------------------------------
    def connect_arduino(self, port):
        """Open the StandardFirmata board on `port`. Every contact is put on Hall
        (the boot state, written again so the record matches the board)."""
        if self.connected:
            print('Hall/DLTS selector is already connected!')
            return 0
        if not port:
            print('Please specify the Hall/DLTS selector port!')
            return -1
        self.board = self.boardFactory(port)
        self.port = port
        self.connected = True
        try:
            sense = self.board.analog[self.POWER_SENSE_PIN]
            sense.register_callback(self._on_power_sample)
            sense.enable_reporting()
            self.board.samplingOn(100)
        except Exception:
            self.powerLevel = None           # relay_power() then reports "unknown"
        self.set_state(*self.set_pins(self.configurations('hall')))
        return 0

    def disconn_arduino(self, to_hall=False):
        """Close the board. The routing is left as it is unless to_hall=True."""
        if not self.connected:
            print('Nothing to do!')
            return 0
        if to_hall:
            self.set_state(*self.set_pins(self.configurations('hall')))
        try:
            self.board.exit()
            self.board.sp.close()
        finally:
            self.board = None
            self.connected = False
        return 0

    def _on_power_sample(self, value):
        self.powerLevel = value

    # ---- routing ---------------------------------------------------------------
    def set_mode(self, mode):
        """'hall' or 'dlts' for all four contacts. Switch only with the
        instrument outputs off."""
        return self.set_state(*self.set_pins(self.configurations(mode)))

    def set_channel(self, contact, position):
        """One contact: contact 1-4 or 'P1'-'P4'; position 'A' (Hall) or 'B' (DLTS)."""
        contact = str(contact).upper()
        if not contact.startswith('P'):
            contact = 'P' + contact
        return self.set_state(*self.set_pins({contact: position}))

    def get_state(self):
        """Positions last written {'P1': 'A'|'B', ...}."""
        return dict(self.positions)

    def get_mode(self):
        """'hall', 'dlts' or 'mixed', from the positions last written."""
        values = set(self.positions.values())
        if values == {'A'}:
            return 'hall'
        if values == {'B'}:
            return 'dlts'
        return 'mixed'

    def relay_power(self):
        """True / False from the A0 power sense, or None before the first sample."""
        if self.powerLevel is None:
            return None
        return self.powerLevel >= self.POWER_ON_LEVEL

    def require_mode(self, mode):
        """None if the sample is routed to `mode`, else the reason. For a run's
        setup check (planned). With relay power off every contact is on Hall."""
        mode = str(mode).lower()
        if not self.connected:
            return 'Hall/DLTS selector is not connected'
        current = self.get_mode()
        if current != mode:
            return f'Hall/DLTS selector is in {current.upper()} mode, not {mode.upper()}'
        if mode == 'dlts' and self.relay_power() is False:
            return 'Hall/DLTS selector RELAY POWER switch is off (every contact is on Hall)'
        return None

    def routing_table(self):
        """Text table: each contact, its position and what it is connected to."""
        lines = ['Contact  Position  Connected to']
        for c, p in self.positions.items():
            to = 'Arduino switch box (Keithley)' if p == 'A' else self.DLTS_CABLING[c]
            lines.append(f'{c:<9}{p} ({self.POSITION_NAMES[p]}){"":<2}{to}')
        return '\n'.join(lines)


selector = HallDltsSelector()
CONTROL_PINS = HallDltsSelector.CONTROL_PINS
DLTS_CABLING = HallDltsSelector.DLTS_CABLING


def configurations(mode):
    return selector.configurations(mode)


def set_pins(P):
    return selector.set_pins(P)


def set_state(pinsDict, pinMap=None):
    return selector.set_state(pinsDict, pinMap)


def connect_arduino(port):
    return selector.connect_arduino(port)


def disconn_arduino(to_hall=False):
    return selector.disconn_arduino(to_hall)


def set_mode(mode):
    return selector.set_mode(mode)


def set_channel(contact, position):
    return selector.set_channel(contact, position)


def get_state():
    return selector.get_state()


def get_mode():
    return selector.get_mode()


def relay_power():
    return selector.relay_power()


def require_mode(mode):
    return selector.require_mode(mode)


def routing_table():
    return selector.routing_table()


if __name__ == '__main__':
    print('Hall/DLTS selector Lib is loaded')
    print(routing_table())
