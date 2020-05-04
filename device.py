#!/usr/bin/env python3

from binascii import hexlify
from configparser import ConfigParser
import sys
from time import sleep
from zag import *
from queue import Queue, Empty
from random import randint
from time import time

class Device(object):
    def __init__(self, port):
        self.dev = DEV(port)
        _, self.long_addr = self.dev.get_object(DEV.Param.long_addr, 8)
        print('I\'m %s' % (hexlify(self.long_addr).decode('utf8').upper()),)

        self.config = ConfigParser()
        self.load_config()

        self.dsn = randint(0, 255)
        self.packet = None

        self.dev.set_value(DEV.Param.channel, self.channel)
        self.dev.set_value(DEV.Param.rx_mode, 0)
        self.dev.set_value(DEV.Param.tx_mode, DEV.TxMode.send_on_cca)
        self.dev.set_leds(0xFF, 0)

    def load_config(self):
        self.config.read('device.ini')
        self.channel = int(self.config.get('device', 'channel', fallback='11'))
        self.panid = int(self.config.get('device', 'panid', fallback='0xFFFF'), 0)
        self.coordinator = int(self.config.get('device', 'coordinator', fallback='0xFFFF'), 0)
        self.service = int(self.config.get('device', 'service', fallback=-1), 0)
        self.ssid = self.config.get('device', 'ssid', fallback=None)

    def save_config(self):
        with open('coordinator.ini', 'w') as config_file:
            self.config.write(config_file)

    def send_packet_wait_ack(self, packet):
        self.packet = packet
        self.packet_last = time()
        self.packet_retry = 0
        self.packet_seq = self.dsn
        self.dev.send_packet(packet)

    def send_ack(self, seq_num):
        mhr = MHR()
        mhr.frame_control |= MHR.FrameType.ack << MHR.FrameControl.type
        mhr.seq_num = seq_num
        packet += mhr.encode()
        self.dev.send_packet(packet)

    def send_beacon_request(self):
        mhr = MHR()
        mhr.frame_control |= MHR.FrameType.cmd << MHR.FrameControl.type
        mhr.frame_control |= MHR.AddrMode.short << MHR.FrameControl.dst_mode
        mhr.seq_num = self.dsn
        mhr.dst_panid = 0xFFFF
        mhr.dst_addr = 0xFFFF
        packet = mhr.encode()

        cmd = CMD()
        cmd.identifier = CMD.Identifier.bcn_request
        packet += cmd.encode()

        self.dev.send_packet(packet)
        self.dsn = (self.dsn + 1) & 0xFF

    def send_assoc_request(self, panid, short_addr):
        mhr = MHR()
        mhr.frame_control |= MHR.FrameType.cmd << MHR.FrameControl.type
        mhr.frame_control |= 1 << MHR.FrameControl.req_ack
        mhr.frame_control |= MHR.AddrMode.short << MHR.FrameControl.dst_mode
        mhr.frame_control |= MHR.AddrMode.long << MHR.FrameControl.src_mode
        mhr.seq_num = self.dsn
        mhr.dst_panid = panid
        mhr.dst_addr = short_addr
        mhr.src_panid = 0xFFFF
        _, mhr.src_addr = self.dev.get_object(DEV.Param.long_addr, 8)
        packet = mhr.encode()

        cmd = CMD()
        cmd.identifier = CMD.Identifier.association_request
        cmd.capability |= 1 << CMD.AssocCapability.power_source
        cmd.capability |= 1 << CMD.AssocCapability.idle_recv
        cmd.capability |= 1 << CMD.AssocCapability.allocate_address
        packet += cmd.encode()

        self.send_packet_wait_ack(packet)
        self.dsn = (self.dsn + 1) & 0xFF

    def bcn_handler(self, mhr, bcn, payload):
        if self.panid <= 0xFFFD:
            return
        if mhr.frame_control >> MHR.FrameControl.src_mode & 0x3 != MHR.AddrMode.short:
            return
        if mhr.frame_control >> MHR.FrameControl.dst_mode & 0x3 != MHR.AddrMode.none:
            return
        if mhr.src_panid > 0xFFFD:
            return
        if mhr.src_addr > 0xFFFD:
            return
        if not bcn.superframe & BCN.Superframe.pan_coordinator:
            return
        if not bcn.superframe & BCN.Superframe.association_permit:
            return
        if self.ssid != None and self.ssid != bcn.ssid:
            return
        if self.service not in bcn.services:
            return
        self.send_assoc_request(mhr.src_panid, mhr.src_addr)

    def packet_handler(self, packet, rssi):
        debug_packet(packet)

        mhr, payload = MHR.decode(packet)
        if mhr.frame_control & 0x7 == MHR.FrameType.ack:
            if self.packet and mhr.seq_num == self.packet_seq:
                self.packet = None
                self.packet_retry = 0
        elif mhr.frame_control & 0x7 == MHR.FrameType.bcn:
            bcn, payload = BCN.decode(payload)
            self.bcn_handler(mhr, bcn, payload)

    def button_handler(self, button):
        if button == 1:
            self.send_beacon_request()

    def loop(self):
        try:
            while True:
                try:
                    event, data = self.dev.event_queue.get(timeout=0.25)
                    if event == DEV.Event.on_packet:
                        self.packet_handler(*data)
                    elif event == DEV.Event.on_button:
                        self.button_handler(*data)
                except Empty:
                    pass

                now = time()

                if self.packet and self.packet_last + 0.25 <= now:
                    self.packet_last = now
                    if self.packet_retry < 10:
                        self.dev.send_packet(self.packet)
                        self.packet_retry += 1
                    else:
                        self.packet = None

        except KeyboardInterrupt:
            self.dev.shutdown()


if __name__ == '__main__':
    coordinator = Device(sys.argv[1])
    coordinator.loop()
