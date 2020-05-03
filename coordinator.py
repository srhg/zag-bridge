#!/usr/bin/env python3

from binascii import hexlify, unhexlify
from configparser import ConfigParser
import sys
from time import sleep
from zag import *
from queue import Queue
from random import randint


class Coordinator(object):
    def __init__(self, port):
        self.dev = DEV(port)
        _, self.long_addr = self.dev.get_object(DEV.Param.long_addr, 8)
        print('I\'m %s' % (hexlify(self.long_addr).decode('utf8').upper()),)

        self.config = ConfigParser()
        self.load_config()

        if self.panid == 0xFFFF:
            self.panid = randint(0, 0xFFFD)
            self.save_config()

        self.short_addr = 0x0000
        self.bsn = randint(0, 255)
        self.dsn = randint(0, 255)

        self.dev.set_value(DEV.Param.channel, self.channel)
        self.dev.set_value(DEV.Param.rx_mode, 0)
        self.dev.set_value(DEV.Param.tx_mode, DEV.TxMode.send_on_cca)

    def load_config(self):
        self.config.read('coordinator.ini')
        self.channel = int(self.config.get('coordinator', 'channel', fallback='11'))
        self.panid = int(self.config.get('coordinator', 'panid', fallback='0xFFFF'), 0)
        self.services = [int(n) for n in self.config.get('coordinator', 'services', fallback='0').split(',')]
        self.services.sort()
        self.ssid = self.config.get('coordinator', 'ssid', fallback='Sample')
        self.devices = {}
        if not self.config.has_section('devices'):
            self.config.add_section('devices')
        for short_addr, long_addr in self.config.items('devices'):
            self.devices[short_addr] = unhexlify(long_addr.encode('utf8'))

    def save_config(self):
        self.config['coordinator']['panid'] = '0x%04X' % self.panid
        for short_addr, long_addr in self.devices.items():
            self.config['devices']['0x%04X' % short_addr] = hexlify(long_addr).decode('utf8')
        with open('coordinator.ini', 'w') as config_file:
            self.config.write(config_file)

    def send_bcn(self):
        mhr = MHR()
        mhr.frame_control |= MHR.FrameType.bcn << MHR.FrameControl.type
        mhr.frame_control |= MHR.AddrMode.short << MHR.FrameControl.src_mode
        mhr.seq_num = self.bsn
        mhr.src_panid = self.panid
        mhr.src_addr = self.short_addr
        packet = mhr.encode()

        bcn = BCN()
        bcn.superframe |= 15 << BCN.Superframe.bcn_order
        bcn.superframe |= 15 << BCN.Superframe.superframe_order
        bcn.superframe |= 1 << BCN.Superframe.pan_coordinator
        bcn.superframe |= 1 << BCN.Superframe.association_permit
        bcn.ssid = self.ssid
        bcn.services = self.services
        packet += bcn.encode()

        self.dev.send_packet(packet)
        self.bsn = (self.bsn + 1) & 0xFF

    def send_association_response(self, long_addr):
        short_addr = 0xFFFF
        for short, long in self.devices.items():
            if long == long_addr:
                short_addr = int(short, 0)

        status = CMD.AssocStatus.assoc_success
        if short_addr > 0xFFFD:
            if len(self.devices) >= 0xFFFD:
                short_addr == 0xFFFF
                status = CMD.AssocStatus.pan_at_capacity
            else:
                while True:
                    short_addr = randint(0, 0xFFFD)
                    if short_addr == self.short_addr:
                        continue
                    if short_addr not in self.devices:
                        break
                self.devices[short_addr] = long_addr
                self.save_config()

        mhr = MHR()
        mhr.frame_control |= MHR.FrameType.cmd << MHR.FrameControl.type
        mhr.frame_control |= 1 << MHR.FrameControl.req_ack
        mhr.frame_control |= 1 << MHR.FrameControl.panid_compression
        mhr.frame_control |= MHR.AddrMode.long << MHR.FrameControl.dst_mode
        mhr.frame_control |= MHR.AddrMode.long << MHR.FrameControl.src_mode
        mhr.seq_num = self.dsn
        mhr.dst_panid = self.panid
        mhr.dst_addr = long_addr
        mhr.src_panid = self.panid
        mhr.src_addr = self.long_addr
        packet = mhr.encode()
        
        cmd = CMD()
        cmd.identifier = CMD.Identifier.association_response
        cmd.short_addr = short_addr
        cmd.status = status
        packet += cmd.encode()

        self.dev.send_packet(packet)
        self.dsn = (self.dsn + 1) & 0xFF

    def bcn_request_handler(self, mhr, cmd):
        if mhr.frame_control >> MHR.FrameControl.src_mode & 0x3 != MHR.AddrMode.none:
            return
        if mhr.frame_control >> MHR.FrameControl.dst_mode & 0x3 != MHR.AddrMode.short:
            return
        if mhr.dst_panid != 0xFFFF:
            return
        if mhr.dst_addr != 0xFFFF:
            return
        self.send_bcn()

    def association_request_handler(self, mhr, cmd):
        if not mhr.frame_control & (1 << MHR.FrameControl.req_ack):
            return
        if mhr.frame_control >> MHR.FrameControl.dst_mode & 0x3 != MHR.AddrMode.short:
            return
        if mhr.frame_control >> MHR.FrameControl.src_mode & 0x3 != MHR.AddrMode.long:
            return
        if mhr.dst_panid != self.panid:
            return
        if mhr.dst_addr != self.short_addr:
            return
        if mhr.src_panid != 0xFFFF:
            return
        self.send_association_response(mhr.src_addr)

    def cmd_handler(self, mhr, cmd, payload):
        if cmd.identifier == CMD.Identifier.bcn_request:
            self.bcn_request_handler(mhr, cmd)
        elif cmd.identifier == CMD.Identifier.association_request:
            self.association_request_handler(mhr, cmd)

    def packet_handler(self, packet, rssi):
        debug_packet(packet)

        mhr, payload = MHR.decode(packet)
        if mhr.frame_control & 0x7 == MHR.FrameType.cmd:
            cmd, payload = CMD.decode(payload)
            self.cmd_handler(mhr, cmd, payload)

    def button_handler(self, button):
        self.dev.set_leds(1<<button, ~self.dev.get_leds() & 0xFF)

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
    coordinator = Coordinator(sys.argv[1])
    coordinator.loop()
