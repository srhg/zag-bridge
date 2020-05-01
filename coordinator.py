#!/usr/bin/env python3

from binascii import hexlify
import sys
from time import sleep
from zag import *
from queue import Queue


class Coordinator(object):
    def __init__(self, port):
        self.device = Device(port)
        _, short = self.device.get_value(Device.Param.short_addr)
        _, ext = self.device.get_object(Device.Param.long_addr, 8)
        print('I\'m 0x%04X, %s' % (short, hexlify(ext).decode('utf8').upper()))

        self.device.set_value(Device.Param.channel, 11)
        self.device.set_value(Device.Param.rx_mode, 0)
        self.device.set_value(Device.Param.tx_mode, Device.TxMode.send_on_cca)

    def packet_handler(self, data, rssi):
        mhr, offset = MHR.decode(data)
        l = []
        for k, v in vars(mhr).items():
            if isinstance(v, int):
                v = f'0x{v:X}'
            else:
                v = repr(v)
            l.append('%s:%s' % (k, v))
        print(', '.join(l) + ' - ' + data[offset:].decode('utf8'))

    def button_handler(self, button):
        self.device.set_leds(1<<(button - 1), ~self.device.get_leds() & 0xFF)

    def loop(self):
        try:
            while True:
                event, data = self.device.event_queue.get()
                if event == Device.Event.on_packet:
                    self.packet_handler(*data)
                elif event == Device.Event.on_button:
                    self.button_handler(*data)
        except KeyboardInterrupt:
            self.device.shutdown()


if __name__ == '__main__':
    coordinator = Coordinator(sys.argv[1])
    coordinator.loop()
