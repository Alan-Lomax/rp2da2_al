"""RP2 local detector main.py

:author: Paul Redhead

This is the main entry point for the RP2 application running a layout distributed pico. 
It starts the MQTT client and the RailCom block detector objects on the first core.
It also starts the screen on the second core.

All interrupt service routines and timer callbacks run on core 0.  No pre-emptive code
runs on core 1.

It is designed to run on the Raspberry Pi Pico2 W.
The Wi-Fi radio interface uses a PIO state machine. The Pico W doesn't have enough state
machines for concurrent Wi-Fi and quad RailCom.
It uses the micropython,  _thread, sys, network and asyncio libraries.
It also uses the dcc_rc_ch1, neoled, screen, mqtt_cmd, mqtt, mqtt_client, and device modules.
"""
"""       Copyright 2025  Paul Redhead

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
# python imports
import _thread, sys, network, asyncio

# micropython imports 
from micropython import alloc_emergency_exception_buf

# lib imports
from device import Device
from screen import Screen
from led_pio import BlkLed

# DCC and RailCom imports
from dcc_rc_ch1 import RComBlkDet
from dcc_rc_pio import RailComRead
from blk_mon import DCCBlkDet

# MQTT imports
from mqtt import Will
from mqtt_lcl import Block, Sensor
from mqtt_client import MQTTClient

from wifi import WiFi

alloc_emergency_exception_buf(100)

def screen_splash():
    """Create screen splash.
    
    It's done here to avoid unnessesary imports in screen modules.
    """
    hostname = network.hostname()
    ssid = WiFi.get_instance().get_ssid()
    t0 = (0, '  DCC ', 0)
    t1 = (1, '', 0)
    t2 = (2, f'{ssid} {hostname}', 0)
    t3 = (3, 'Standalone', 0)
    # override defaults.
    for _, dev in Device.get_items():
        if dev.get_type() == MQTTClient.DEVICE_TYPE:
            t3 = (3, f'MQTT {dev.get_broker()}', 0)
        elif dev.get_type() == RailComRead.LCL_DEVICE_TYPE:
            t1 = (1, 'RailCom Block', 0)
    return (t0, t1, t2, t3)


def build_config(blocks):
    """
    Build the configuration.

    Many objects that are part of the configuration are instantiated here. A
    list of mqtt agents that reference these objects is returned.

    Objects are instantiated in order. I.e. the first object gets the first set of
    hardware resournces such as GPIO pins and so on.

    For track blocks both RailCom detectors and current based occupancy detectors are instantiated.
    
    args:
        blocks: List of block names in order

    returns:
        list of mqtt agents to be started
    """
    build = sys.implementation._build # get MicroPython build details
    if build.find("PICO") == -1:
        raise RuntimeError("Unsupported Platform")
    rx_pin = [14, 16, 18, 20]  # pin numbers for RailCom RX (orientation is pin + 1)
    state_machine = [0, 2, 4, 6]  # state machine numbers for RailCom channel timers
    m_lst = []
    i = 0
    for blk_name in blocks:
        led = BlkLed(i + 1) # first led reserved for comms status
        # DCC power sense pin is 27 - common to all blocks
        m_lst.append(Block(RComBlkDet(blk_name, state_machine[i], rx_pin[i], led, 27)))
        m_lst.append(Sensor(DCCBlkDet(blk_name, i, led)))
        i = i + 1
    m_lst.append(Will("track/state", MQTTClient.QOS1))
    return m_lst

async def main():
    """Main function for the RP2 first core (core 0) application.

    Hardware allocations are defined for IO Pins and PIO State machines.
    This function sets up the MQTT client and starts the main loop.
    MQTT agents are set for the channel 1 block detectors.
    """
    # this runs forever
    await MQTTClient.get_instance().run(build_config(('1011', '1012', '1013', '1014')))


def main1():
    """ Main function for the RP2 second core (core 1) application.
    
    This function sets up the screen.
    It also enters a loop to read event reports and update the screen.
    """
    s = Screen().get_instance()
    s.show_screen(screen_splash())

    while True:
        report = Device.get_event_report() # wait until event received
        s.show_event(report)

if __name__ == '__main__':
    _thread.start_new_thread(main1,())
    asyncio.run(main())
