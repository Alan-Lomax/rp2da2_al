"""Block Detector Screen Module
    :author: Paul Redhead

 
This is the screen application module.  It specifies the Screen class.

Generally it provides application specific access to the display. It knows about application objects and events etc.
and how they are managed on screen.

It specifies menus, menu items and other popups.
"""
"""       Copyright 2023, 2024  Paul Redhead

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

from oled0_91 import OLED_0in91

from machine import I2C


from dcc_rc_ch1 import RComBlkDet
from dcc_rc_ch2 import RComCmdRsp

class Screen():
    """This class provides the screen application.
    
    It deals with the application events that
    require display on the screen or other actions (e.g. UI menu/data)

    It's a singleton.

    """

    _scrn = None # this will be set to the singleton object on instantiation

    _CV_LU = {(8, 151):"ESU", (8, 145):"ZIMO", (8, 78):"TOM"}
    

    @classmethod
    def get_instance(cls):
        """Return the singleton instance

        The singleton is created on the first call.
        
        args:
            cls:
            """
        if cls._scrn is None:
            cls._scrn = Screen()
        return cls._scrn
        

    def __init__(self):
        """Screen Initialiser
        
        This displays the start up splash.

        """
        if (Screen._scrn) != None and (Screen._scrn is not self):
            raise RuntimeError ('Only one Screen object possible')
        
        self._oled = OLED_0in91(I2C(0))
        self._oled.page[0].text('RailCom Demo', 0, 0)
        self._oled.page[1].fill(0)
        self._oled.page[2].fill(0)
        self._oled.page[3].fill(0)
        self._oled.show()

        


    def show_event(self, report):
        """Show an event report
        
        This updates the screen with the event.  Other application actions on events are 
        dealt with elsewhere.

        Args:
            self:
            report: a tuple containing the reference to the source object, the unique event code see: display
                and additional information - format and content event specific
        """
    
        (source, event, data) = report
        self._event_handler[event](self, source, data)






    def _handle_blk_empty(self,src, _):
        self._oled.page[0].fill(0)
        self._oled.page[0].text(f'{src.get_name()} empty', 0, 0)
        self._oled.show_page(0)

    def _handle_blk_ch1(self,src, data):
        addr_t, address, orientation = data
        self._oled.page[0].fill(0)
        self._oled.page[0].text(f'{src.get_name()} {addr_t}{address} {orientation}', 0, 0)
        self._oled.show_page(0)

    def _handle_blk_occ(self,src, _):
        self._oled.page[0].fill(0)
        self._oled.page[0].text(f'{src.get_name()} occupied', 0, 0)
        self._oled.show_page(0)

    def _handle_cv_val(self,src, data):
        address, cv_num, value = data
        self._oled.page[1].fill(0)
        try:
            self._oled.page[1].text(f'a:{address} {Screen._CV_LU[(cv_num, value)]}', 0, 0)
        except KeyError:
            self._oled.page[1].text(f'a:{address} c:{cv_num} v:{value}', 0, 0)
        self._oled.show_page(1)

    def _handle_pom_to(self,src, data):
        address, cv_num = data
        self._oled.page[1].fill(0)
        self._oled.page[1].text(f'a:{address} c:{cv_num} timeout', 0, 0)
        self._oled.show_page(1)

    def _handle_pom_nak(self,src, data):
        address, cv_num = data
        self._oled.page[1].fill(0)
        self._oled.page[1].text(f'a:{address} c:{cv_num} NAK', 0, 0)
        self._oled.show_page(1)

    _event_handler = {RComBlkDet.BLK_EMPTY: _handle_blk_empty,
                      RComBlkDet.BLK_OCC:_handle_blk_occ,
                      RComBlkDet.BLK_CH1: _handle_blk_ch1,
                      RComCmdRsp.POM_CV: _handle_cv_val,
                      RComCmdRsp.POM_TO: _handle_pom_to,
                      RComCmdRsp.POM_NAK: _handle_pom_nak}