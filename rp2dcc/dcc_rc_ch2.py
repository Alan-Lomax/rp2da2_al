"""DCC RailCom DCC Command Response
    :author: Paul Redhead

This module contains the functions and classes for DCC RailCom DCC command mobile responses on Channel 2.

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

import time
from micropython import const

from dcc_rc_pio import RailComRead
from dcc_cmd_util import CommandPacket, CV_Access
from device import Device




_DG2_LEN = {0:1, 1:1, 2:1, 3:5, 4:5, 7:2, 8:5, 9:5, 10:5, 11:5, 12:5, 13:5, 14:1}
""" Channel 2 Datagram Length

This is for mobile decoders - see RCN217  Table 6. The table for accessory (static) decoders
differs, but no plans to support them yet.

Indexed by datagram id, contains the additional number of 6 bit groups to be concatenated.
"""




class RComCmdRsp(Device):
    """Channel 2 (Command Response) Decode
    
    This runs on the command station. As there is only one DCC generator there can only be
    one of these too.

    Datagram identifiers for channel 2 are defined in RCN-217 3.1 Table 6.

    Attributes:
        DG_POM: POM response (CV value) datagram identifier.
        DG_DYN: dynamic info (DG ID 7) datagram identifier.
        DYN_REAL_SPEED0: real speed part 1 datagram identifier.
        DYN_REAL_SPEED1: real speed part 2 datagram identifier.
        DYN_RECEP_STATS: reception stats datagram identifier.


    """
    # class constants
    # datagrams and contents
    DG_POM = const(0)       # datagram with POM response (CV value)
    DG_DYN = const(7)       # datagram with dynamic info (DG ID 7)
    DYN_REAL_SPEED0 = const(0) # real speed part 1
    DYN_REAL_SPEED1 = const(1) # real speed part 2
    DYN_RECEP_STATS = const(7) # reception stats

    # event codes
    POM_CV    = const(30)   # CV value from read or write
    POM_TO    = const(31)   # POM access timeout


    def __init__(self, rc_sm_num, rx_pn, enable_pn):
        """DCC Command object constructor
        

        The enable pin is that used to enable the DRV8874. It's set by the DCC generator PIO.
        It's monitored here by the PIO program as
        it's low going edge marks the start of the cutout.

        The RailCom reader for channel 2 is instantiated and the base class is initiated.

        Note:
            The RailCom reader will use two sequentially numbered state machines - the first is supplied.

            The RailCom reader will use two sequentially numbered GPIO pins for receiving - the first is supplied.

        
        
        Args:
            self:
            rc_sm_num: first state machine number to be used RailCom receiver functions.
            rx_pn:  First pin number for RailCom rx
            enable_pn: Pin number that enables the DRV8874 - it's only read here
        """



        self._rc = RailComRead(rc_sm_num,
                              rx_pn,  self._rail_com_ch2_msg, 2, enable_pn)
        
        self._rc_msg = {}   # most recently received message by address
        self._speed = {}    # dynamic speed by address 
        self._recep_stats = {}  # decoder reported reception stats by address
        self._pom_acc = {}   # outstanding cv accesss requests by command type/address


        self.errors = {'lu':0, 'df':0, 'ic':0} # error counts
        """Error counts by error type."""
        super().__init__('cmd', 'r')



    def _rail_com_ch2_msg(self, buffer, detector_side):
        """Handle RailCom Message Callback
        
        This callback is called on termination of the RailCom Channel 2 message receipt window,
        whether a message has been received or not. The addressed decoder returns a channel 2
        message. Other mobile decoders remain silent.

        TODO:
            confirm whether interpretting detector side useful in Ch2 context

        args:
            self:
            buffer:   translated data
            detector_side: orientation of DCC decoder wrt DCC signal
        
        """
        cmd = CommandPacket.get_last_command()
        if cmd is None:
            # no point in continuing if we don't know what command was issued
            return
        address = cmd.get_address()
        if cmd.get_type() == CV_Access.TYPE:
            # maybe already there (second write) - quietly update or add
            # get the request cv number and command timeout and save
            # the decoder has half a second to respond RCN217 5.1
            self._pom_acc[(address)] = (cmd.get_cv(), time.ticks_add(time.ticks_ms(), 500))
        else:
            # other command
            # check for outstanding POM command timeout
            try:
                cv, timeout = self._pom_acc[(address)] # get timeout
                if time.ticks_diff(time.ticks_ms(), timeout) > 0:
                    # timeout expired
                    del(self._pom_acc[(address)]) # no longer needed
                    self.report_event(RComCmdRsp.POM_TO, (address, cv + 1))
            except KeyError:
                # no outstanding POM command
                pass



        # last command was to the broadcast address - no response expected
        # (unless we start looking at accessories too)
        if len(buffer) == 0:
            # no data
            return
        self._act_on_datagram(self._parse_cg2_msg(buffer, detector_side), address)
        
        
        


    def _parse_cg2_msg(self, buff, d_side):
        """ Parse channel 2 message
        
        Inspect the message and extract datagrams which are saved in list and returned.
        """ 
        buff_iter = iter(buff)
        dg_id = None
        # preset for implicit ack
        protocol_byte = RailComRead.IMP_ACK
        datagram = list()

        try:
            while True:
                # StopIteration will end the loop
                b = next(buff_iter)
                # separate the datagram id and first 2 bits of payload
                dg_id = (b & 0xFC)  >> 2
                dg_payload = b & 0x03
                try:
                    error = False
                    for _ in range(_DG2_LEN[dg_id]):
                        b = next(buff_iter)
                        if b == RailComRead.ERR_LU:
                            # original byte was invalid Hamming weight 4
                            self.errors['lu'] += 1
                            protocol_byte = b
                            error = True
                        elif b > 0x3f:
                            # datagram can't include protocol control byte
                            self.errors['ic'] += 1
                            protocol_byte = RailComRead.ERR_RESP
                            error = True # so this and any more are ignored
                        elif error:
                            pass
                        else:
                            dg_payload = (dg_payload << 6) + b # append sextet to payload
                    # payload complete
                    if not error:
                        datagram.append((dg_id,dg_payload))
                    #dg_id = None  # set back to None to mark datagram complete
                except KeyError: # not datagram - assume it's a protocol byte
                    if protocol_byte == RailComRead.IMP_ACK:
                        protocol_byte = b # overwrite implicit ack
                    elif protocol_byte == RailComRead.ACK and b == RailComRead.NAK:
                        # RCN-217 says this is possible!
                        protocol_byte = RailComRead.CV_ERR
                dg_id = None  # set back to None to mark datagram complete


        except StopIteration:
            if dg_id is not None:
                # datagram not complete - ignore it - duff format
                # other earlier datagrams in same message will be processed 
                self.errors['df'] +=1


        # add overal response datagrams
        datagram.append((RailComRead.DG_RESP, protocol_byte))
        # create dg for side if set - this isn't really relevant to Ch2 
        # maybe remove
        datagram.append((RailComRead.DG_SIDE, d_side))
        return datagram

    def _act_on_datagram(self, datagram, addr):
        """Take action on datagram"""
        
        for dg in datagram:
            if dg == (RailComRead.DG_RESP, RailComRead.NO_RESP):
                # quietly ignore no response - there can be no others
                return  

            id, payload = dg
            if id == RComCmdRsp.DG_DYN:
                # dynamic information RCN217 5.5
                dyn_si = payload & 0x3F # extract subindex
                value = payload >> 6
                if dyn_si <= 1: # speed subindex 0 or 1
                    self._speed[addr] = value + (dyn_si << 8)
                elif dyn_si == RComCmdRsp.DYN_RECEP_STATS:
                    self._recep_stats[addr] = value
                else:
                    pass # other dynamics ignored at present
            elif id == RComCmdRsp.DG_POM:
                # POM cv response RCN219 5.1
                # payload is cv value from last POM command
                # check that there was one for this address
                try:
                    cv, _= self._pom_acc[(addr)]
                    del(self._pom_acc[(addr)]) # no longer needed
                    self.report_event(RComCmdRsp.POM_CV, (addr, cv + 1, payload))
                except KeyError:
                    pass

        # save the last received datagrams            
        self._rc_msg[addr] = (datagram)



        