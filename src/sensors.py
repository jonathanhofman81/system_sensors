#!/usr/bin/env python3

import re
import csv
import time
import pytz
import psutil
import socket
import platform
import datetime as dt
from subprocess import check_output

try:
    from rpi_bad_power import new_under_voltage
    rpi_power_disabled = False
except ImportError:
    rpi_power_disabled = True

try:
    import apt
    apt_disabled = False
except ImportError:
    apt_disabled = True


try:
    import pySMART
    smartctl_disabled = False
except ImportError:
    smartctl_disabled = True

def static_vars(**kwargs):
    def decorate(func):
        for k in kwargs:
            setattr(func, k, kwargs[k])
        return func
    return decorate

# Get OS information
OS_DATA = {}
with open('/etc/os-release') as f:
    reader = csv.reader(f, delimiter='=')
    for row in reader:
        if row:
            OS_DATA[row[0]] = row[1]

old_net_data = psutil.net_io_counters()
previous_time = time.time() - 10
UTC = pytz.utc
DEFAULT_TIME_ZONE = None

if not rpi_power_disabled:
    _underVoltage = new_under_voltage()

def as_local(dattim: dt.datetime) -> dt.datetime:
    """Convert a UTC datetime object to local time zone."""
    if dattim.tzinfo == DEFAULT_TIME_ZONE:
        return dattim
    if dattim.tzinfo is None:
        dattim = UTC.localize(dattim)

    return dattim.astimezone(DEFAULT_TIME_ZONE)

def utc_from_timestamp(timestamp: float) -> dt.datetime:
    """Return a UTC time from a timestamp."""
    return UTC.localize(dt.datetime.utcfromtimestamp(timestamp))

def get_last_boot():
    return str(as_local(utc_from_timestamp(psutil.boot_time())).isoformat())

def get_last_message():
    return str(as_local(utc_from_timestamp(time.time())).isoformat())


@static_vars(last_update_check=dt.datetime.min, available_updates=0)
def get_updates():
    #this is a time consuming function, check only once every hour
    now = dt.datetime.now()

    print(f"Update check: lastime: {get_updates.last_update_check}, now: {now}")
    if (now - get_updates.last_update_check) > dt.timedelta(hours=1):
        print(f"Update check: More than one hour passed since last check. Checking available updates....")
        get_updates.last_update_check = now

        # check amound of updates
        cache = apt.Cache()
        cache.open(None)
        cache.upgrade()
        get_updates.available_updates = cache.get_changes().__len__()

    return str(get_updates.available_updates)

# Temperature method depending on system distro
def get_temp():
    temp = '';
    if 'rasp' in OS_DATA['ID']:
        reading = check_output(['vcgencmd', 'measure_temp']).decode('UTF-8')
        temp = str(re.findall('\d+.\d+', reading)[0])
    else:
        reading = check_output(['cat', '/sys/class/thermal/thermal_zone0/temp']).decode('UTF-8')
        temp = str(reading[0] + reading[1] + '.' + reading[2]) # why?? need linux system to test
    return temp

# Clock speed method depending on system distro
def get_clock_speed():
    clock_speed = '';
    if 'rasp' in OS_DATA['ID']:
        reading = check_output(['vcgencmd', 'measure_clock','arm']).decode('UTF-8')
        clock_speed = str(int(re.findall('\d+', reading)[1]) / 1000000)
    else: # need linux system to test
        reading = check_output(['cat', '/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq']).decode('UTF-8')
        clock_speed = str(int(re.findall('\d+', reading)[0]) / 1000)
    return clock_speed

def get_disk_usage(path):
    return str(psutil.disk_usage(path).percent)


def get_memory_usage():
    return str(psutil.virtual_memory().percent)


def get_load(arg):
    return str(psutil.getloadavg()[arg])

def get_net_data(arg):
    global old_net_data
    global previous_time
    current_net_data = psutil.net_io_counters()
    current_time = time.time()
    if current_time == previous_time:
        current_time += 1
    net_data = (current_net_data[0] - old_net_data[0]) / (current_time - previous_time) * 8 / 1024
    net_data = (net_data, (current_net_data[1] - old_net_data[1]) / (current_time - previous_time) * 8 / 1024)
    previous_time = current_time
    old_net_data = current_net_data
    net_data = ['%.2f' % net_data[0], '%.2f' % net_data[1]]
    return net_data[arg]

def get_cpu_usage():
    return str(psutil.cpu_percent(interval=None))

def get_swap_usage():
    return str(psutil.swap_memory().percent)

def get_wifi_strength():  # check_output(['/proc/net/wireless', 'grep wlan0'])
    wifi_strength_value = check_output(
                              [
                                  'bash',
                                  '-c',
                                  'cat /proc/net/wireless | grep wlan0: | awk \'{print int($4)}\'',
                              ]
                          ).decode('utf-8').rstrip()
    if not wifi_strength_value:
        wifi_strength_value = '0'
    return (wifi_strength_value)

def get_wifi_ssid():
    ssid = check_output(
                              [
                                  'bash',
                                  '-c',
                                  '/usr/sbin/iwgetid -r',
                              ]
                          ).decode('utf-8').rstrip()
    if not ssid:
        ssid = 'UNKNOWN'
    return (ssid)

def get_rpi_power_status():
    return _underVoltage.get()

def get_hostname():
    return socket.gethostname()

def get_host_ip():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(('8.8.8.8', 80))
        return sock.getsockname()[0]
    except socket.error:
        try:
            return socket.gethostbyname(socket.gethostname())
        except socket.gaierror:
            return '127.0.0.1'
    finally:
        sock.close()

def get_host_os():
    try:
        return OS_DATA['PRETTY_NAME']
    except:
        return 'Unknown'

def get_host_arch():
    try:
        return platform.machine()
    except:
        return 'Unknown'

def get_hdd_temp(path):
    print(f"hdd temp path: '{path}'")
    sd = pySMART.Device(path)
    if sd.attributes[190] is not None:
        return str(sd.attributes[190].raw)
    elif sd.attributes[194] is not None:
        return str(sd.attributes[194].raw)
    return "not available"

def get_hdd_tbw(path):
    print(f"hdd tbw path: '{path}'")
    sd = pySMART.Device(path)
    if sd.attributes[241] is not None:
        return str(round(int(sd.attributes[241].raw) * 512 / 1024 /1024 / 1024))
    return "not available"

sensors = {
          'temperature': 
                {'name':'Temperature',
                 'class': 'temperature',
                 'unit': '°C',
                 'icon': 'thermometer',
                 'sensor_type': 'sensor',
                 'function': get_temp},
          'clock_speed':
                {'name':'Clock Speed',
                 'unit': 'MHz',
                 'sensor_type': 'sensor',
                 'function': get_clock_speed},
          'disk_use':
                {'name':'Disk Use',
                 'unit': '%',
                 'icon': 'micro-sd',
                 'sensor_type': 'sensor',
                 'function': lambda: get_disk_usage('/')},
          'memory_use':
                {'name':'Memory Use',
                 'unit': '%',
                 'icon': 'memory',
                 'sensor_type': 'sensor',
                 'function': get_memory_usage},
          'cpu_usage':
                {'name':'CPU Usage',
                 'unit': '%',
                 'icon': 'memory',
                 'sensor_type': 'sensor',
                 'function': get_cpu_usage},
          'load_1m':
                {'name': 'Load 1m',
                 'unit': u"\u200B", # dummy unit (zero whitespace) to display graph
                 'icon': 'cpu-64-bit',
                 'sensor_type': 'sensor',
                 'function': lambda: get_load(0)},
          'load_5m':
                {'name': 'Load 5m',
                 'unit': u"\u200B", # dummy unit (zero whitespace) to display graph
                 'icon': 'cpu-64-bit',
                 'sensor_type': 'sensor',
                 'function': lambda: get_load(1)},
          'load_15m':
                {'name': 'Load 15m',
                 'unit': u"\u200B", # dummy unit (zero whitespace) to display graph
                 'icon': 'cpu-64-bit',
                 'sensor_type': 'sensor',
                 'function': lambda: get_load(2)},
          'net_tx':
                {'name': 'Network Upload',
                 'unit': 'Kbps',
                 'icon': 'server-network',
                 'sensor_type': 'sensor',
                 'function': lambda: get_net_data(0)},
          'net_rx':
                {'name': 'Network Download',
                 'unit': 'Kbps',
                 'icon': 'server-network',
                 'sensor_type': 'sensor',
                 'function': lambda: get_net_data(1)},
          'swap_usage':
                {'name':'Swap Usage',
                 'unit': '%',
                 'icon': 'harddisk',
                 'sensor_type': 'sensor',
                 'function': get_swap_usage},
          'power_status':
                {'name': 'Under Voltage',
                 'class': 'problem',
                 'sensor_type': 'binary_sensor',
                 'function': get_rpi_power_status},
          'last_boot':
                {'name': 'Last Boot',
                 'class': 'timestamp',
                 'icon': 'clock',
                 'sensor_type': 'sensor',
                 'function': get_last_boot},
          'hostname':
                {'name': 'Hostname',
                 'icon': 'card-account-details',
                 'sensor_type': 'sensor',
                 'function': get_hostname},
          'host_ip':
                {'name': 'Host IP',
                 'icon': 'lan',
                 'sensor_type': 'sensor',
                 'function': get_host_ip},
          'host_os':
                {'name': 'Host OS',
                 'icon': 'linux',
                 'sensor_type': 'sensor',
                 'function': get_host_os},
          'host_arch':
                {'name': 'Host Architecture',
                 'icon': 'chip',
                 'sensor_type': 'sensor',
                 'function': get_host_arch},
          'last_message':
                {'name': 'Last Message',
                 'class': 'timestamp',
                 'icon': 'clock-check',
                 'sensor_type': 'sensor',
                 'function': get_last_message},
          'updates': 
                {'name':'Updates',
                 'icon': 'cellphone-arrow-down',
                 'sensor_type': 'sensor',
                 'function': get_updates},
          'wifi_strength': 
                {'class': 'signal_strength',
                 'name':'Wifi Strength',
                 'unit': 'dBm',
                 'icon': 'wifi',
                 'sensor_type': 'sensor',
                 'function': get_wifi_strength},
          'wifi_ssid': 
                {'class': 'signal_strength',
                 'name':'Wifi SSID',
                 'icon': 'wifi',
                 'sensor_type': 'sensor',
                 'function': get_wifi_ssid},
}