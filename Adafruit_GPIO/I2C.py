# Copyright (c) 2014 Adafruit Industries
# Author: Tony DiCola
# Based on Adafruit_I2C.py created by Kevin Townsend.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
import logging
import subprocess
import time

import smbus

import Adafruit_GPIO.Platform as Platform


def reverseByteOrder(data):
    """Reverses the byte order of an int (16-bit) or long (32-bit) value."""
    # Courtesy Vishal Sapre
    byteCount = len(hex(data)[2:].replace('L','')[::2])
    val       = 0
    for i in range(byteCount):
        val    = (val << 8) | (data & 0xff)
        data >>= 8
    return val

def get_default_bus():
    """Return the default bus number based on the device platform.  For a
    Raspberry Pi either bus 0 or 1 (based on the Pi revision) will be returned.
    For a Beaglebone Black the first user accessible bus, 1, will be returned.
    """
    plat = Platform.platform_detect()
    if plat == Platform.RASPBERRY_PI:
        if Platform.pi_revision() == 1:
            # Revision 1 Pi uses I2C bus 0.
            return 0
        else:
            # Revision 2 Pi uses I2C bus 1.
            return 1
    elif plat == Platform.BEAGLEBONE_BLACK:
        # Beaglebone Black has multiple I2C buses, default to 1 (P9_19 and P9_20).
        return 1
    elif plat == Platform.CHIP:
        # CHIP has 2 user accessible I2C busses, default to 2 (U1425 and U14_26)
        # We want the CHIP to default to 2 as the PocketCHIP header breaks out
        # this interface
        # But, the CHIP Pro defaults to bus 1
        import CHIP_IO.Utilities as UT
        if UT.is_chip_pro():
            return 1
        else:
            return 2
    else:
        raise RuntimeError('Could not determine default I2C bus for platform.')

def get_i2c_device(address, busnum=None, **kwargs):
    """Return an I2C device for the specified address and on the specified bus.
    If busnum isn't specified, the default I2C bus for the platform will attempt
    to be detected.
    """
    if busnum is None:
        busnum = get_default_bus()
    return Device(address, busnum, **kwargs)

def require_repeated_start():
    """Enable repeated start conditions for I2C register reads.  This is the
    normal behavior for I2C, however on some platforms like the Raspberry Pi
    there are bugs which disable repeated starts unless explicitly enabled with
    this function.  See this thread for more details:
      http://www.raspberrypi.org/forums/viewtopic.php?f=44&t=15840
    """
    plat = Platform.platform_detect()
    if plat == Platform.RASPBERRY_PI:
        # On the Raspberry Pi there is a bug where register reads don't send a
        # repeated start condition like the kernel smbus I2C driver functions
        # define.  As a workaround this bit in the BCM2708 driver sysfs tree can
        # be changed to enable I2C repeated starts.
        subprocess.check_call('chmod 666 /sys/module/i2c_bcm2708/parameters/combined', shell=True)
        subprocess.check_call('echo -n 1 > /sys/module/i2c_bcm2708/parameters/combined', shell=True)
    # Other platforms are a no-op because they (presumably) have the correct
    # behavior and send repeated starts.


class Device(object):
    """Class for communicating with an I2C device using the smbus library.
    Allows reading and writing 8-bit, 16-bit, and byte array values to registers
    on the device."""
    def __init__(self, address, busnum):
        """Create an instance of the I2C device at the specified address on the
        specified I2C bus number."""
        self._address = address
        self._bus = smbus.SMBus(busnum)
        self._logger = logging.getLogger('Adafruit_I2C.Device.Bus.{0}.Address.{1:#0X}' \
                                .format(busnum, address))

    def writeRaw8(self, value):
        """Write an 8-bit value on the bus (without register)."""
        value = value & 0xFF
        try:
            self._bus.write_byte(self._address, value)
            self._logger.debug("Wrote 0x%02X",
                     value)
        except IOError, err:
            self._logger.exception("error in writeRaw8: %s", err)
            time.sleep(0.001)

    def write8(self, register, value):
        """Write an 8-bit value to the specified register."""
        value = value & 0xFF
        try:
            self._bus.write_byte_data(self._address, register, value)
            self._logger.debug("Wrote 0x%02X to register 0x%02X",
                     value, register)
        except IOError, err:
            self._logger.exception("error in write8: %s", err)
            time.sleep(0.001)

    def write16(self, register, value):
        """Write a 16-bit value to the specified register."""
        value = value & 0xFFFF
        try:
            self._bus.write_word_data(self._address, register, value)
            self._logger.debug("Wrote 0x%04X to register pair 0x%02X, 0x%02X",
                     value, register, register+1)
        except IOError, err:
            self._logger.exception("error in write16: %s", err)
            time.sleep(0.001)

    def writeList(self, register, data):
        """Write bytes to the specified register."""
        try:
            self._bus.write_i2c_block_data(self._address, register, data)
            self._logger.debug("Wrote to register 0x%02X: %s",
                     register, data)
        except IOError, err:
            self._logger.exception("error in writeList: %s", err)
            time.sleep(0.001)

    def readList(self, register, length):
        """Read a length number of bytes from the specified register.  Results
        will be returned as a bytearray."""
        try:
            results = self._bus.read_i2c_block_data(self._address, register, length)
            self._logger.debug("Read the following from register 0x%02X: %s",
                     register, results)
            return results
        except IOError, err:
            self._logger.exception("error in readList: %s", err)
            time.sleep(0.001)

    def readRaw8(self):
        """Read an 8-bit value on the bus (without register)."""
        try:
            result = self._bus.read_byte(self._address) & 0xFF
            self._logger.debug("Read 0x%02X",
                    result)
            return result
        except IOError, err:
            self._logger.exception("error in readRaw8: %s", err)
            time.sleep(0.001)

    def readU8(self, register):
        """Read an unsigned byte from the specified register."""
        try:
            result = self._bus.read_byte_data(self._address, register) & 0xFF
            self._logger.debug("Read 0x%02X from register 0x%02X",
                     result, register)
            return result
        except IOError, err:
            self._logger.exception("error in readU8: %s", err)
            time.sleep(0.001)

    def readS8(self, register):
        """Read a signed byte from the specified register."""
        try:
            result = self.readU8(register)
            if result > 127:
                result -= 256
            return result
        except IOError, err:
            self._logger.exception("error in readS8: %s", err)
            time.sleep(0.001)

    def readU16(self, register, little_endian=True):
        """Read an unsigned 16-bit value from the specified register, with the
        specified endianness (default little endian, or least significant byte
        first)."""
        try:
            result = self._bus.read_word_data(self._address,register) & 0xFFFF
            self._logger.debug("Read 0x%04X from register pair 0x%02X, 0x%02X",
                           result, register, register+1)
            # Swap bytes if using big endian because read_word_data assumes little
            # endian on ARM (little endian) systems.
            if not little_endian:
                result = ((result << 8) & 0xFF00) + (result >> 8)
            return result
        except IOError, err:
            self._logger.exception("error in readU16: %s", err)

    def readS16(self, register, little_endian=True):
        """Read a signed 16-bit value from the specified register, with the
        specified endianness (default little endian, or least significant byte
        first)."""
        try:
            result = self.readU16(register, little_endian)
            if result > 32767:
                result -= 65536
            return result
        except IOError, err:
            self._logger.exception("error in readS16: %s", err)
            time.sleep(0.001)

    def readU16LE(self, register):
        """Read an unsigned 16-bit value from the specified register, in little
        endian byte order."""
        try:
            return self.readU16(register, little_endian=True)
        except IOError, err:
            self._logger.exception("error in readU16LE: %s", err)
            time.sleep(0.001)

    def readU16BE(self, register):
        """Read an unsigned 16-bit value from the specified register, in big
        endian byte order."""
        try:
            return self.readU16(register, little_endian=False)
        except IOError, err:
            self._logger.exception("error in readU16BE: %s", err)
            time.sleep(0.001)

    def readS16LE(self, register):
        """Read a signed 16-bit value from the specified register, in little
        endian byte order."""
        try:
            return self.readS16(register, little_endian=True)
        except IOError, err:
            self._logger.exception("error in readS16LE: %s", err)
            time.sleep(0.001)

    def readS16BE(self, register):
        """Read a signed 16-bit value from the specified register, in big
        endian byte order."""
        try:
            return self.readS16(register, little_endian=False)
        except IOError, err:
            self._logger.exception("error in readS16BE: %s", err)
            time.sleep(0.001)
