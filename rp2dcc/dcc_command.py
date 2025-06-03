"""DCC module
    :author: Paul Redhead

This module provides high level APIs. It and associated modules in the package contain the functions
and classes for DCC command station.

A command comprises a preamble, one or more instruction/data bytes and an error detection (checksum) byte.
Each byte is preceeded by a single '0' bit.
The checksum is followed by a single '1' bit which may be the initial bit of
the next preamble. The preamble is at least 14 '1' bits. Note that in this implementation the pre-amble is
not interrupted by the cutout so the preamble length doesn't need to be lengthened.


This DCC implementation has a limited set of features.  E.g. it doesn't include bit stretching
for DC vehicles on address 0, 14/28 speed steps, any service mode functions or accessory controller
commands. We allow for a maximum command sequnece of 11 bytes including check sum. There is limited
support for Programming on Main.

RCN-210 &  RCN-211 partly apply as appropriate. 

See also NMRA Standards S 9.2 and S 9.2.1. S 9.2.1.1 is not supported.

The module makes full use of a RP2xx0 PIO for DCC signal encoding and serialisation. If RailCom is enabled
a second PIO is used for this. 

The DCC commands are serialised to the track via the DCC generation driver, which also inserts
the RailCom cutout if in use.


Three RP2040 PIO state machines are used by driver modules, one for DCC generation and
two for RailCom. The two RailCom state machines must be on the same PIO block. 


"""
"""        Copyright (C) 2023, 2024, 2025 Paul Redhead

        This program is free software: you can redistribute it and/or modify it
        under the terms of the GNU General Public License as published by the Free Software Foundation, 
        either version 3 of the License, or (at your option) any later version.
        This program is distributed in the hope that it will be useful,
        but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
        See the GNU General Public License for more details.
        You should have received a copy of the GNU General Public License along with this program.
        If not, see <http://www.gnu.org/licenses/>.
"""


from micropython import const
from machine import Pin, ADC
from device import Device


from dcc_cmd_util import SpeedCommand, FGrp1Command, CommandPacket, IdlePacket, CV_Access

from dcc_cmd_pio import DCCCmdTx


class DCCCommand():
    """ DCC Command

    This class manages the DCC command packets. It provides the APIs for the registration
    of DCC commands to be serialised. It performs the scheduling and tranmission of
    command packets.


    
    Attributes:
        FWD:    Forward direction
        REV:    Reverse direction
        ON:     Power On
        OFF:    Power Off
        
    """

    # class constants - may be imported by other modules
    FWD = const(1)
    REV = const(-1)

    ON = const(1)
    OFF = const(0)
    
    
    def __init__(self, DCC_pn, sleep_pn, gen_sm_num, enable_pn = None):
        """DCC Command object constructor
        
        This initialises the DCC command manager singleton.  An attempt to create a 2nd
        instance will cause a runtime error.
        
        Pins and timers are initialised. The dictionary for the packet list is created and the 
        FIFO buffer allocated.

        If the enable pin is not supplied, it must be hard wired to true (high) on the DRV8874 and 
        RailCom related parameters will be ignored if they are supplied.
        The enable pin, and RailCom channel 2 processor must be supplied for RailCom.
        
        Args:
            self:
            DCC_pn: Pin number allocated for DCC output.
            sleep_pn: Pin number allocated to the booster for powering the track
            gen_sm_num: PIO state machine number to be used for DCC Generation
            enable_pn: Pin number to enable the DRV8874.
        """

        # The packet list is used for commands that are currently scheduled for 
        # transmission. Speed & function commands are never deleted but POM commands have
        # limitied life span 
        self._packet_list = {}              # create empty dictionary
        self._pom_packet = None             # and no outstanding pom command
        # instantiate dcc generator
        # we use the entire PIO memory so only one state machine and the choice is arbitary!
        self._dcc_gen_pio = DCCCmdTx(gen_sm_num, DCC_pn, sleep_pn, enable_pn)
 
        self._idle_packet = IdlePacket()    # create an idle packet

        self._active_address = set() # acive mobile decoders

        # Set up interrupt on enable pin to schedule next packet when 
        # cutout period ends.
        enable_pn.irq(self._nxt_packet, Pin.IRQ_RISING)


    def power(self, p = None):
        """DCC Power On/Off

        Start and stop command packet transmission scheduling.
        PIO stop start and power to track delegated to the DCC tx class (pio_pwr).
        
        args:
            p: 1 for power on, 0 for power off, None for get power status

        returns:
            power status as held by the DCC generator

        """
        if p is None:
            return self._dcc_gen_pio.pio_pwr()
        
        r = self._dcc_gen_pio.pio_pwr(p)  # start pio before send!

        if p == DCCCmdTx.ON:
            # the normal sequence of command packets will be triggered at the completion of the
            # idle packet
            self._idle_packet.send()
            # set an iterator
            self._packet_iter = iter(self._packet_list)

        # no specific action here for power off

        return r


    def set_speed(self, address, dir, speed = 0):
        """Set Speed (including direction)
        
        If there is a speed command object for the adressed decoder in the list already
        the object is updated otherwise a new speed command is created.  The input is validated.
        The packet generated will be for a 128 step speed setting and
        decoders must be configured for 28/128 speed steps.

        See NMRA S-9.2.1  Section 2.3.2.1
        
        args:
            self:
            address: the address of the decoder - may be short or long
            dir:    the direction - forward or reverse
            speed: the speed to be set - range 0 to 127 - default 0
              
        returns:
            True if validation is passed and the command is added to the list or modified. False
            if validation fails.
        """
        # a bit of defensive programming
        if address < 1 or address > CommandPacket.MAX_LONG_ADDR:
            return False
        if speed < 0 or speed > 127:
            return False
        if not dir in (DCCCommand.FWD, DCCCommand.REV):
            return False
        
        # speed direction packet list entry's key is 'S', address
        # speed / direction packet - 1 or 2 address bytes, 2 instruction bytes
    
        try:
            self._get_cmd((SpeedCommand.TYPE, address)).update(dir, speed)
        except KeyError:
            self._add_cmd(SpeedCommand(address, dir, speed))

        return True

            
    def set_fg1(self, address, f_num, state):
        """Set Function Group 1
        
        This sets or clears a function in group 1.  The forward light is usually function 
        number 0.

        If there is a function group 1 command in the packet list for the addressed decoder it is
        updated. Otherwise the command is added to the list.

        See NMRA S-9.2.1  Section 2.3.4
        
        args:
            self:
            address: the address of the decoder - may be short or long
            f_num:  function number to set or clear
            state:  1 for set, 0 for clear

        returns:
            True if validation is passed and the command is added to the list or modified. False
            if validation fails.   
        """
        # a bit of defensive programming
        if address < 1 or address > CommandPacket.MAX_LONG_ADDR:
            return False
        if f_num < 0 or f_num > 4:
            return False
        if not state in (0, 1):
            return False

        # function group 1 packet - single instruction byte
        try:
            self._get_cmd((FGrp1Command.TYPE, address)).update(f_num, state)
        except KeyError:
            self._add_cmd(FGrp1Command(address, f_num, state))

        return True
    

    def read_cv(self, address, cv_num):
        """Read CV (POM)
        
        This initiates reading a CV using Programming on Main in conjunction with RailCom.

        The command is validated and the read request scheduled for action. The addressed
        decoder must be active and the command will be rejected by the command generator class
        this is not true.

        args:
            self:
            address:
            cv_num: cv number as entered - users count from 1, DCC counts from 0!

        """

        if not (1 <= cv_num <= 1024):
            return False
        return self._pom_cmd(CV_Access(address, cv_num
                                        - 1))
    
    def write_cv(self, address, cv_num, new_val):
        """Write CV (POM)
        
        This initiates writing a CV using Programming on Main in conjunction with RailCom.

        The command is validated and the write request scheduled for action. The addressed
        decoder must be active and the command will be rejected by the command generator class
        this is not true.

        args:
            self:
            address:
            cv_num: cv number as entered - users count from 1, DCC counts from 0!
            new_val: the new value for the CV

        """
        if not (1 <= cv_num <= 1024):
            return False
        if not (0 <= new_val <= 255):
            return False
        return self._pom_cmd(CV_Access(address, cv_num - 1, operation = 'w', value = new_val))
        
    
    def _get_cmd(self, key):
        """Get a command from the packet list
        
        raises KeyError if not found
        """
        return self._packet_list[key]
    

    def _add_cmd(self, command):
        """Add Command to Packet List"""
        type = command.get_type()
        addr = command.get_address()
        self._packet_list[(type, addr)] = command
        self._active_address.add(addr)


    def _pom_cmd(self, command):
        """Process Program on Main command

        The response to a POM command may be delayed. The decoder does not have to put the POM
        response in the immediately following window and may respond following a subsequent command to that
        decoder.
        
        To ensure that there is a subsequent command the address is checked to see if in the active list.
        The command will be rejected if the address is not in the active list or
        there is a POM command already being processed.

        return:
            True if command accepted
            False if command rejected
        """
        addr = command.get_address()
        if addr not in self._active_address:
            return False
        if self._pom_packet is not None:
            # POM commands are temporary and only 1 is allowed
            return False
        self._pom_packet = command
        return True


    def _nxt_packet(self, _):
        """ Generate next packet - soft interrupt or timer callback.
        
        This is called when the nenext packet in the
        list is to be serialised out on the DCC interface. If the list is empty the DCC
        Idle packet is serialised or if the next packet is unavailable (e.g. being updated).

        The function is triggered via a soft ISR.  If RailCom is enabled, this is connected to be enable
        pin rising indicating the end of the cutout period assocated with the preceding command.

        TODO:
        If RailCom not enabled this will be triggered by the PIO program itself when serialising the packet
        end bit. 
        
        This function instructs the next Command object in the list to send its command.
        """
        Device.check_core0()
        if self._dcc_gen_pio.pio_pwr() == DCCCmdTx.OFF:
            # power now off - don't transmit.
            return
        #ts = time.ticks_us()
        if len(self._packet_list) == 0:
            # list empty send the DCC idle packet
            self._idle_packet.send()
            return
        
        if self._pom_packet is None:
            # POM packet if there takes precidence

            try:
                # get the next packet in the list
                packet_key = next(self._packet_iter)
            except StopIteration:
                # at end of list - renew iterator
                self._packet_iter = iter(self._packet_list)
                packet_key = next(self._packet_iter)
            # send the command
            #t1 = time.ticks_us() - ts
            result = self._packet_list[packet_key].send()
        else:
            result = self._pom_packet.send()

        if result == CommandPacket.NOT_SENT:
            self._idle_packet.send() # send idle packet instead
        elif result == CommandPacket.SENT_POM:
            # POM commands get deleted once sent
            self._pom_packet = None
        # else nothing to do if normal command sent OK
        return



if __name__ == '__main__':
    import _thread, time, os
    from dcc_rc_ch1 import RComBlkDet
    from dcc_rc_ch2 import RComCmdRsp

    from screen import Screen

    # DRV8874 pin allocations - common to Pico & Arduino Nano Connect
    enable_pin = Pin(18, Pin.OUT, value = 1)
    sleep_pin = Pin(19, Pin.OUT, value = 0)   # set sleep mode initially
    dcc_pin = Pin(20, Pin.OUT)
    fault_pin = Pin(21, Pin.IN, Pin.PULL_UP)  # low for true
    sense_pin = ADC(Pin(26)) # current sense input

    machine = os.uname().machine # get machine description

    if machine.find("Pico") > -1:
        # Detector pin allocations - Raspberry Pi Pico format
        c2_rx_pin = Pin(16, Pin.IN)
        c1_rx_pin = Pin(14, Pin.IN)
    elif machine.find("Nano") > -1:
        # Detector pin allocations - Arduino Nano  format
        c2_rx_pin = Pin(15, Pin.IN)
        c1_rx_pin = Pin(0, Pin.IN)
    else:
        print (machine, "invalid")


    time_stamp = time.ticks_ms()

    rc_ch1 = RComBlkDet(4, c1_rx_pin, enable_pin)

    rc_ch2 = RComCmdRsp(6, c2_rx_pin, enable_pin)
    
    dcc = DCCCommand(dcc_pin, sleep_pin, 0, enable_pin)

    def main1():
        s = Screen()
        
        while True:
            s.show_event(Device.get_event_report())

    def print_stats(reset = True):
        global time_stamp
        elapsed_time = time.ticks_diff(time.ticks_ms(), time_stamp)  
        print("** Commands **")
        counts = CommandPacket.get_counts()
        total = sum(counts.values())
        print(f"Rate: {(total) * 1000 / elapsed_time:.2f} per sec")
        print(counts)

        print("** Channel 1 **")
        print("datagrams:",rc_ch1.get_dg_list())
        counts = rc_ch1.get_error_counts()
        print("errors   :", counts)
        print(f"err. rate: {(sum(counts.values())/total):.0%}")
        print("** Channel 2 **")
        print("datagrams:",rc_ch2.get_dg_list())
        counts = rc_ch2.get_error_counts()
        print("errors   :", counts)
        print(f"err. rate: {(sum(counts.values())/total):.0%}")
        if reset:
            rc_ch1.reset_stats()
            rc_ch2.reset_stats()
            CommandPacket.reset_counts()
            time_stamp = time.ticks_ms()



    _thread.start_new_thread(main1,())





