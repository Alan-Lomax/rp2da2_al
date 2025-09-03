"""MQTT Control and Utilities

:author: Paul Redhead

This module provides access to the MQTT interface via MQTT agents which manage subscriptions and
publications on behalf of relevant hardware and applications software.

This module provides common functions. e.g. the abstract base class for MQTT agents. 

MQTT version 3.1.1 as documented https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.html
        
QoS2 not supported - only QoS0 or 1

Sessions are clean - i.e. no context saved between sessions. 

Subscriptions are static.  The subscription list is passed to the client at instantiation and is
immutable.
"""
"""       Copyright 2023, 2024, 2025  Paul Redhead

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


from micropython import const

from mqtt_client import MQTTClient


from dcc_rc_ch1 import RComBlkDet


class MQTTAgent():
    """ MQTT Agent

    This is a virtual class acting as the base for MQTT agents that set up subscriptions,
    process received publications and publish.
    """


    # too early to call get_instance 
    _dcc = None
    # but OK here because get_instance will instantiate the client
    _client = MQTTClient.get_instance()
    
    def __init__(self, topic_filter, QoS):
        """Initialise the subscription

        Args:
            topic_filter: the topic filter to match against received topics
            QoS: the Quality of Service for this subscription.  Must be either MQTTClient.QoS0 or MQTTClient.QoS1

        """
        self._topic_filter = topic_filter
        self._QoS = QoS

    def matches(self, topic):
        """check if topic matches filter

        Parse the received topic against the topic filter to see if it
        matches.

        '+' matches a single item in the topic name.
        '#' matches any remaining topic name including none

        Args:
            self:
            topic: the received topic as a string

        Returns:
            True if matches else false
        """
        topic_iter = iter(topic.split('/'))
        for filter_item in self._topic_filter.split('/'):
            try:
                topic_item = next(topic_iter)
            except StopIteration:
                 # '#' matches null string but otherwise topic list is too short
                return(filter_item == '#')
                   
            # '#' wild card - must be last and matches rest of topic
            if filter_item == '#':
                return True
            # '+' wild card - matches this item only
            if filter_item != '+' and filter_item != topic_item:
                # neither wild card topic nor match
                return False
        return True
    
    def get_filter(self):
        """Get the topic filter for this subscription
        
        Returns:
            The topic filter as a string
        """
        return (self._topic_filter)
    
    def handle_publication(self, topic, dup_flag, ret_flag, payload):
        """ Handle a publication

        This method is called by the MQTT client when a publication is received.
        It must be implemented by the derived class. 

        Args:
            topic: the topic of the publication
            dup_flag: True if this is a duplicate publication
            ret_flag: True if this is a retained publication
            payload: the payload of the publication as a string
        """
        raise NotImplementedError
    
    def pub_check(self):
        """ Publication check
        
        Check to see if agent has anything to publish and publish it.
        
        This is the default version for those agents that do not publish.
        It should be overridden in the derived class for any agent that publishes.

        returns:
            False if nothing published
        """
        return False


class Will(MQTTAgent):
    """Manage Will Subscription

    The subscription is used to handle the MQTT will message when published by the broker on behalf
    of another client that has gone off line (e.g. jmri). The subscription is remote client specific
    and an instance is required for each remote client to be monitored.
    
    This agent does not publish. 
    """

    def __init__(self, topic_filter, QoS):
        """Initialise the will subscription

        Args:
            topic_filter: the topic filter to match against received topics
            QoS: the Quality of Service for this subscription.  Must be either MQTTClient.QoS0 or MQTTClient.QoS1
        """
        super().__init__(topic_filter, QoS)

    def handle_publication(self, topic, dup_flag, ret_flag, payload):
        """Handle will publication
        
        This method is called by the MQTT client when a will publication is received.
        :TODO: What to do with this?

        Args:
            topic: the topic of the publication
            dup_flag: True if this is a duplicate publication
            ret_flag: True if this is a retained publication
            payload: the payload of the publication as a string
        """
        pass

class Block(MQTTAgent):
    """Block Subscription 

    This subscription is used to handle publications to the block topic.
    """
    SENSOR_TOPIC_PREFIX = "track/sensor"
    REPORTER_TOPIC_PREFIX = "track/reporter"

    SENSOR_PAYLOAD = {RComBlkDet.BLK_EMPTY:"INACTIVE",
                       RComBlkDet.BLK_OCC:"ACTIVE",
                       RComBlkDet.BLK_CH1:"ACTIVE"}

    def __init__(self, rc_block):
        self._rc_block = rc_block # RailCom block
        self._name = rc_block.get_name()
        self._last_block_state = None
        super().__init__(f'{Block.SENSOR_TOPIC_PREFIX}/{self._name}/set', MQTTClient.QoS1)

    def handle_publication(self, topic, dup_flag, ret_flag, payload):
        """Handle a publication
        This method is called by the MQTT client when a publication is received.
        Args:
            topic: the topic of the publication
            dup_flag: True if this is a duplicate publication
            ret_flag: True if this is a retained publication
            payload: the payload of the publication as a string
        """
        print("Sensor", topic, payload)

    def pub_check(self):
        """Publication check
        
        Check to see if block state has changed and publish it.
        
        returns:
            True if the agent has published else False
        """
        # Get the current block state from the channel 1 detector
        current_block_state = self._rc_block.get_block_state()
        if current_block_state == self._last_block_state:
            return False
        # Publish the new block state
        try:
            tx_payload = Block.SENSOR_PAYLOAD[current_block_state[0]]
        except KeyError:
            # not valid status (yet)
            return
        if not self._client.publish(f'{Block.SENSOR_TOPIC_PREFIX}/{self._name}/event',
                                 tx_payload, False, MQTTClient.QoS1):
            return False # publish failed - retry later
        self._last_block_state = current_block_state
        if current_block_state[0] == RComBlkDet.BLK_CH1:
            # channel 1 info available
            self._client.publish(f'{Block.REPORTER_TOPIC_PREFIX}/{self._name}',
                                 f'{current_block_state[1][1]} {current_block_state[1][2]}',
                                 False, MQTTClient.QoS1)
        else:
            # clear reporter info
            self._client.publish(f'{Block.REPORTER_TOPIC_PREFIX}/{self._name}',
                        '', False, MQTTClient.QoS1)

        return True        
