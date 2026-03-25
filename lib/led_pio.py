"""LED Module

This module provides the classes for the driving string connected LEDs such as NeoPixel etc.

Each string is driven by a single GPIO pin.  We use NeoPixels as on board indicators and as such
we only expect a short string of LEDs and there will only be one string per board.

This version uses a PIO state machine to drive the LEDs.

Only one string of max. length five LEDs is supported on GPIO 22 

"""
"""       Copyright 2025, 2026  Paul Redhead

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

from machine import Pin
from micropython import const
import rp2
import array

from device import Device

# pyright: reportUndefinedVariable=false


@rp2.asm_pio(sideset_init=rp2.PIO.OUT_LOW,
             out_shiftdir=rp2.PIO.SHIFT_LEFT,
             autopull=True, pull_thresh=24)
def ws2812_tx():
    T1 = 2
    T2 = 5
    T3 = 3

    wrap_target()
    label("bitloop")
    out(x, 1)               .side(0)    [T3 - 1]
    jmp(not_x, "do_zero")   .side(1)    [T1 - 1]
    jmp("bitloop")          .side(1)    [T2 - 1]
    label("do_zero")
    nop()                   .side(0)    [T2 - 1]
    wrap()


_MAX_LEN = const(5)
_PIN = 22
_SM = 5 # State Machine number for RP2040 (Pico, PicoW etc) 
_SM_P2 = 9 # State Machine number for RP2350 (Pico2, Pico2W)


class NeoLed():
    """ NeoPixel Led
    
    This class controls a single LED on the chain.

    RGB values may either be passed as a tuple or a single colour may be set or cleared.

    Setting a colour without a value will set the maximum(255).  Clearing a colour will set 0.
    
    Attributes:
        LED_R: Red
        LED_G: Green
        LED_B: Blue
        
    """
    LED_R = const(0)
    LED_G = const(1)
    LED_B = const(2)

    COMMS_LED = 0
    DCC_LED = 1

    DEFAULT_B = const(50) # full brightness is rather bright!

    def __init__(self, string_index):
        """Initialise the NeoPixel class

        This sets the initial RGB.

        args:
            string_index: The index of the LED in the string.
        """
        self._rgb = [0, 0, 0]   # set initial RGB values.
        self._string = NeoString.get_instance()
        self._i = string_index
        try:
            self._string.set_rgb(string_index, tuple(self._rgb))
        except IndexError:
            # ignore invalid index
            pass

    def set(self, colour, flush = True, *, val = DEFAULT_B):
        """Set the colour of the LED

        This sets a colour (red, green or blue) and brightness value.
        args:
            colour: The colour to set.  This should be one of NeoLed.LED_R, NeoLed.LED_G or NeoLed.LED_B.
            val: The value to set the colour to.  This should be an integer between 0 and 255.
                 If not specified, it defaults to NeoLed.DEFAULT_B.
        """
        try:
            self._rgb[colour] = val
            self._string.set_rgb(self._i, tuple(self._rgb))
            if flush:
                # write up to and including this LED
                self._string.write(self._i + 1)  
        except KeyError:
            # quietly ignore invalid colour
            pass

    def clear(self, colour, flush = True):
        """Clear a colour from the LED  

        This clears the colour of the LED
        args:
            colour: The colour to clear.  This should be one of NeoLed.LED_R, NeoLed.LED_G or NeoLed.LED_B.
        """
        try:
            self._rgb[colour] = 0
            self._string.set_rgb(self._i, tuple(self._rgb))
            if flush:
                self._string.write(self._i + 1)  
        except KeyError:
            # quietly ignore invalid colour
            pass

class BlkLed(NeoLed):
    """ Led used to indicate block status
    
    This controls a NeoString led thats used to indictate overall block status
    as determined by both current sensing and RailCom channed 1 returns
    """

    def __init__(self, string_index):
        super().__init__(string_index)
        self._rc_state = Device.UNKNOWN
        self._oc_state = Device.UNKNOWN

    def update(self, event, data):
        """Update led
        
        The led is updated to reflect the RailCom or current based
        occupancy.
        
        RailCom Ch1 takes precedence.
        args:
            event: event code
            data: associated data"""
        if event == Device.BLK_CH1: # rc ch1 report
            if data is None:
                # no data - empty
                if self._oc_state == Device.BLK_OCC:
                    self.set(NeoLed.LED_G, False) # show occupied - no RC data
                    self._rc_state = Device.BLK_EMPTY
                self.clear(NeoLed.LED_B) # clear RC occupied
                
            else:
                # RC occupied
                self.clear(NeoLed.LED_R, False) # clear no power 
                self.clear(NeoLed.LED_G, False) # suppress current occupied
                self.set(NeoLed.LED_B) # set RC occupied
                self._rc_state = Device.BLK_OCC
        elif event == Device.BLK_OCC: # current detected
            self._oc_state = Device.BLK_OCC
            if self._rc_state != Device.BLK_OCC:
                self.clear(NeoLed.LED_R, False)
                # we can show it
                self.set(NeoLed.LED_G) # show occupied - no RC data
        elif event == Device.BLK_EMPTY: # current lost
            self._oc_state = Device.BLK_EMPTY
            self.clear(NeoLed.LED_R, False) # any event clears no power or ch1 fault 
            if self._rc_state != Device.BLK_OCC:
                # we can show it
                self.clear(NeoLed.LED_G) # show block clear
        elif event == Device.BLK_NPOW: # no power
            self._oc_state = Device.BLK_NPOW
            self.clear(NeoLed.LED_G, False) # suppress current occupied
            self.clear(NeoLed.LED_B, False) # set RC occupied
            self.set(NeoLed.LED_R, val = 10) # not too bright



class NeoString():
    """String of NeoPixels
    
    A singleton class based on the built-in NeoPixel class.
    Although it's a singleton it is explicitly instantiated and get_instance method 
    will not instantiate it automatically.
    This is to allow the string to be created with a specific pin and length.
    The string is a list of NeoLed objects which can be accessed by index.
    The NeoLed objects are used to control the individual LEDs in the string.
    The string is used to control the LEDs on the board.

    If the Arduino tricolour led is available, it's handled independently.
    """

    _this_string = None

    @classmethod
    def get_instance(cls):
        """Return the singleton instance

        If the singleton already exists then it is returned.
        Otherwise it is created
        """
        if cls._this_string is None:
            cls._this_string = NeoString()    


        return cls._this_string

    def __init__(self):
        """Initialise the NeoPixel string
        
        This initialises the NeoPixel string.
        If the singleton already exists then an exception is raised.

        """
        if NeoString._this_string is not None:
            raise RuntimeError("Only one LED string allowed")
        
        self._num_leds = _MAX_LEN
        self._pin = _PIN
        try:
            # is RP2350 state machine available?
            self._sm = rp2.StateMachine(_SM_P2)
        except ValueError:
            # No - go for RP2040 state machine
            self._sm = rp2.StateMachine(_SM)
        
        self._sm.init(ws2812_tx, freq=8_000_000, sideset_base=Pin(_PIN))
        self._sm.active(1)
        self._buff = array.array("I", [0] * _MAX_LEN) # 1 word per led

        self.write()

    def set_rgb(self, i, rgb):
        """Set the RGB value of the LED

        This sets the RGB value of the LED.
        args:
            i: the index number of the led to set
            rgb: A tuple containing the RGB values.  Each value should be an integer between 0 and 255.
        """
        r, g, b = rgb
        self._buff[i] = (g << 16) + (r << 8) + b

    def write(self, count = _MAX_LEN):
        #print(bytes(memoryview(self._buff)[:count]))
        # least sig. 3 bytes contain led values so shift left eight
        self._sm.put(memoryview(self._buff)[:count], 8)


if __name__ == '__main__':
    ps = NeoString.get_instance()
