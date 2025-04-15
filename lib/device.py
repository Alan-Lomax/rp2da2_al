"""Device Module
    :author: Paul Redhead

        Copyright (C) 2023, 2034 Paul Redhead

This provides the Device class, a base class for hardware device drivers and
similar objects.


The RP2040 has two cores (0 and 1).  When running MicroPython by default core 0 is used
and core 1 is idle.  The RP2040 port of MicroPython uses the _thread module to run code
in core 1 and enable communications between the cores.


This module provides a queue for passing events.  Multiple
sources may write to the queue.  There may be only 1 reader.  The reader runs in the main loop.  Sources are 
typically event driven.

If using both cores, core 1 runs a main loop which reads the queue and processess events as they
occur.  Device drivers run on core 0.

"""

# stardard python imports
from collections import deque

# micropython imports
from machine import WDT
import time, _thread
from micropython import const


MAX_Q_LEN = const(16)
"""The capacity of the event queue."""





class ThreadQError(RuntimeError):
    """Thread Queue Error
    
    Raised to indicate adding to the queue failed due to queue full."""
    pass





class Device():
    """Device Base Class
    
    This class acts as a base for hardware devices and similar. In particular those devices which need to raise 
    events for display on the screen or initiate actions as part of automation.  Events are queued.  Although 
    many devices may raise events there is only one reader.  Typically the device class is a abstract class.  I.e not
    instantiated independently.
    
    Attributes:
        """
    # class variables


    # device states 0 & 1 are allocated for hardware devices with binary states e.g. points & relays etc
    UNSET = const(0)
    """State unset / off / false"""
    SET = const(1)
    """State Set / on / true or action complete if > 2 operables states"""
    UNKNOWN = const(2)
    """State unavalable (e.g start of day"""
    INDETERMINATE = const(3)
    """State indeterminate (e.g. action in progress)"""

    # device specific states are defined in the relevant drivers


    
    # _fido = WDT()  # enable a watch dog timer just in case



    _queue = deque((), MAX_Q_LEN, 1)

    #timings = deque((),100)


    

    _q_lock = _thread.allocate_lock()

    


    
    ## empty device table
    # will be added to by devices when instantiated.
    _device_table = {}

    @classmethod 
    def by_name(cls, name):
        """Find a device object by name
        
        Args:
            cls:
            name: the name of the device
            
        Returns:
            refererence to the object
            
        Raises:
            IndexError if not found"""
        return cls._device_table[name]
    
    @classmethod
    def get_items(cls):
        """Get items from the device table.

        The device table holds a list of the device objects keyed by their name.
        
        returns:
            a list of items - name and device object pairs"""
        return cls._device_table.items()
    
    @classmethod
    def get_keys(cls):
        """Get device names (keys) from the device table.

        The device table holds a list of the device objects keyed by their name.
        
        returns:
            a list of device names"""
        return cls._device_table.keys()
    

    @staticmethod
    def check_core0():
        """Check on core 0
        
        'Soft' ISRs associated with timer events and hw related ISRs now appear to run in core 0.
        This implentation assumes this and the method here allows a 'soft' serivice routine to check
        it's on core 0. The get_ident method return core number + 1!
        
        raises:
            Run time error if not on core 0."""
        if _thread.get_ident() != 1:
            raise RuntimeError( "Wrong core")
    
    @classmethod
    def get_event_report(cls, wait = True):
        """ get the event report at top of queue
        
        This is synchronous if wait true and will wait forever while the queue is empty.
        If wait is false it returns None immediately if the queue is empty.
        
        If the queue is not empty the returned tuple holds:
        
            - source, 'self' from the object reporting the event
            - event, one of ACTION_DONE, ACTION_ERROR, ACTION_INIT or as defined for device
            - data, depends on source object and event

        Args:
            cls:
            wait:   if True wait for an event report otherwise return immediately

        Returns:
            None or a tuple



             

        """
       
        '''
        try:
            # see if anything there
            Device._q_lock.acquire()
            event = cls._queue.popleft()
            Device._q_lock.release()
            return(event)
            
        except IndexError:
            Device._q_lock.release()
            # queue empty
            time.sleep_ms(1)
        if not wait:
            return None

        
        Device._q_lock.acquire()
        while len(cls._queue) == 0:
            Device._q_lock.release()
            time.sleep_ms(1)
            # cls._fido.feed()
            Device._q_lock.acquire()
        # queue no longer empty
        event = cls._queue.popleft()
        Device._q_lock.release()
        return(event)
        '''
       
        event = None
        while event is None:
            with Device._q_lock:
                try:
                    event = cls._queue.popleft()
                except IndexError:
                    if not wait:
                        return None
            time.sleep_ms(1)
        return event
        



    def __init__(self, name, type):
        """Initialise Device

        This initialises the device.  Usally invoked by super().__init__() from the child.

        Save the name (should be unique but not formally tested) & type.  Type is a single character. Could
        used __class__ but that would be more complex.

        Args:
            self:
            name: string containing the device name
            type: character specifying the type of device (i.e. class of child)
        
        """
        
        self._name = name
        self._type = type
        Device._device_table[name] = (self)

    def get_name(self):
        """Get the device name
        
        args:
            self:
            
        returns:
            the device name as a string"""
        return self._name
    
    def get_type(self):
        """Get the device type
        
        args:
            self:
            
        returns:
            the device type as a single character string"""
        return self._type
    
    def value(self, v = None):
        """Get or Set the device value
        
        This must be superseded by a bound method in an inheriting class. Otherwise
        a 'not implemented' error will be raised when called.
        
        args:
            self:
            v: the value to be writen if supplied
        
        raises:
            NotImplementedError: if not overridden"""
        
        raise NotImplementedError
    
    def get_state(self):
        """Get the device state
        
        This must be superseded by a bound method in an inheriting class. Otherwise
        a 'not implemented' error will be raised when called.
        
        args:
            self:
        
        raises:
            NotImplementedError: if not overridden"""
        
        raise NotImplementedError


    def report_event(self, event, data):
        """ Add event report to the queue

        The event report is added to the queue.

        :raise ThreadQError:  The queue is full

        args:
            self:
            event:  event code - system specific
            data:   event data to qualify code - device dependent  
            """
        ''''
        try:
            Device._q_lock.acquire()
            Device._queue.append((self, event, data))
            Device._q_lock.release()
        except IndexError:
            Device._q_lock.release()
            raise ThreadQError('Q full')'
        '''
        with Device._q_lock:
            try:
                Device._queue.append((self, event, data))
                return
            except IndexError:
                pass
        raise ThreadQError('Q full')
        
        #Device.trace.append((self, time.ticks_ms(), event))