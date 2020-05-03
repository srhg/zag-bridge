#!/usr/bin/env python3

from binascii import hexlify
from configparser import ConfigParser
import sys
from time import sleep
from zag import *
from queue import Queue
from random import randint

class Device(object):
    def __init__(self, port):
        self.dev = DEV(port)
        _, short = self.dev.get_value(DEV.Param.short_addr)
        _, ext = self.dev.get_object(DEV.Param.long_addr, 8)
        print('I\'m 0x%04X, %s' % (short, hexlify(ext).decode('utf8').upper()))

        with open('config.ini', 'r') as f:
            config_string = '[DEFAULT]\n' + f.read()
        config = ConfigParser()
        config.read_string(config_string)
        self.channel = int(config.get('DEFAULT', 'channel', fallback='11'))
        self.panid = int(config.get('device', 'panid', fallback='0xFFFF'), 0)
        self.coordinator = int(config.get('device', 'coordinator', fallback='0xFFFF'), 0)
        self.service = int(config.get('device', 'service', fallback=-1), 0)
        self.ssid = config.get('device', 'ssid', fallback=None)
        self.dsn = randint(0, 255)

        self.dev.set_value(DEV.Param.channel, self.channel)
        self.dev.set_value(DEV.Param.rx_mode, 0)
        self.dev.set_value(DEV.Param.tx_mode, DEV.TxMode.send_on_cca)

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
        self.dsn += 1

    def send_assoc_req(self, panid, addr):
        mhr = MHR()
        mhr.frame_control |= MHR.FrameType.cmd << MHR.FrameControl.type
        mhr.frame_control |= 1 << MHR.FrameControl.req_ack
        mhr.frame_control |= MHR.AddrMode.short << MHR.FrameControl.dst_mode
        mhr.frame_control |= MHR.AddrMode.long << MHR.FrameControl.src_mode
        mhr.seq_num = self.dsn
        mhr.dst_panid = panid
        mhr.dst_addr = addr
        mhr.src_panid = 0xFFFF
        _, mhr.src_addr = self.dev.get_object(DEV.Param.long_addr, 8)
        packet = mhr.encode()

        cmd = CMD()
        cmd.identifier = CMD.Identifier.association_request
        cmd.capability |= 1 << CMD.AssocCapability.power_source
        cmd.capability |= 1 << CMD.AssocCapability.idle_recv
        cmd.capability |= 1 << CMD.AssocCapability.allocate_address
        packet += cmd.encode()

        self.dev.send_packet(packet)
        self.dsn += 1

    def button_handler(self, button):
        if button == 1:
            self.send_beacon_request()

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

        self.send_assoc_req(mhr.src_panid, mhr.src_addr)

    def packet_handler(self, packet, rssi):
        debug_packet(packet)

        mhr, payload = MHR.decode(packet)
        if mhr.frame_control & 0x7 == MHR.FrameType.bcn:
            bcn, payload = BCN.decode(payload)
            self.bcn_handler(mhr, bcn, payload)

    def loop(self):
        try:
            while True:
                event, data = self.dev.event_queue.get()
                if event == DEV.Event.on_packet:
                    self.packet_handler(*data)
                elif event == DEV.Event.on_button:
                    self.button_handler(*data)
        except KeyboardInterrupt:
            self.dev.shutdown()


if __name__ == '__main__':
    coordinator = Device(sys.argv[1])
    coordinator.loop()
