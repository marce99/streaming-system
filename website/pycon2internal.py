#! /usr/bin/python
# vim: set ts=4 sw=4 et sts=4 ai:

import simplejson
import pprint
import sys
import hashlib
import cStringIO as StringIO
import re
import time

import urllib2

from datetime import datetime, timedelta
import pytz
from dateutil import parser

import markdown

ROOM_MAP = {
    'Grand Ballroom AB': 'ab',
    'Grand Ballroom CD': 'cd',
    'Grand Ballroom EF': 'ef',
    'Grand Ballroom GH': 'gh',
    'Great America':  'america',
    'Great America Floor 2B R1': 'america',
    'Great America Floor 2B R2': 'america',
    'Great America Floor 2B R3': 'america',
    'Great America K': 'america',
    'Great America J': 'america',
#    'Great America K': 'america',
    'Mission City': 'mission',
    'Mission City M1': 'mission',
    'Mission City M2': 'mission',
    'Mission City M3': 'mission',
    'Plenary Hall': 'pyconau',
}

BREAK_NAMES = {
    10: None,
    60: 'Lunch',
    40: 'Morning Break',
    30: ['Morning Break', 'Afternoon Break'],
    190: 'Poster Session',
    920: None,
}

tz = pytz.timezone('Australia/Sydney')
class tzinfo(tz.__class__):
    def __repr__(self):
         return 'pytz.timezone("Australia/Sydney")'
    __str__ = __repr__
tz.__class__ = tzinfo

defaulttime = datetime.now(tz)
convert = markdown.Markdown().convert

def tolower(d):
    newd = {}
    for key, value in d.items():
        if type(value) is dict:
            value = tolower(value)
        newd[key.lower()] = value
    return newd


def parse_duration(s):
    bits = re.split('[^0-9]+', s)
    if len(bits) == 2:
        return timedelta(hours=int(bits[0]), minutes=int(bits[1]))
    elif len(bits) == 3:
        return timedelta(hours=int(bits[0]), minutes=int(bits[1]), seconds=int(bits[2]))


if __name__ == "__main__":
    incoming_json = urllib2.urlopen("http://2013.pycon-au.org/programme/schedule/json").read()
    incoming_data = simplejson.loads(incoming_json)

    # Resort into
    # <room>: (start, end) : <data>
 
    outgoing_data = {}
    while len(incoming_data) > 0:
        item = tolower(incoming_data.pop(0))
        if 'kind' in item and item['kind'] not in ('plenary', 'talk'):
            continue

        roomkey = 'room'
        if roomkey not in item:
            roomkey = 'room name'

        namekey = 'name'
        if namekey not in item:
            namekey = 'title'

        # FIXME: Hack for move room at PyCon US
        if len(item[roomkey].split(',')) > 1:
            for otherroom in item[roomkey].split(','):
               otherroom = otherroom.strip()
               if otherroom == "Mission City":
                   continue
               newitem = dict(item)
               newitem['title'] = "Change to Mission for <b>%s</b>" % newitem[namekey]
               newitem['room'] = otherroom
               newitem['abstract'] = ''
               newitem['conf_url'] += '?'
               incoming_data.insert(0, newitem)

            room = 'Mission City'
        else:
            room = item[roomkey].strip()

        channel = ROOM_MAP.get(room, None)
        if not channel:
            continue
        if channel not in outgoing_data:
            outgoing_data[channel] = {}

        outitem = {}

        outitem['start'] = parser.parse(item['start'], default=defaulttime)
        if 'end' in item:
            outitem['end'] = parser.parse(item['end'], default=defaulttime)
        else:
            outitem['end'] = outitem['start'] + parse_duration(item['duration'])

        if 'conf_url' in item:
            outitem['conf_url'] = item['conf_url']
        else:
            outitem['conf_url'] = str(time.time())

        if item[namekey] == 'Keynote':
            outitem['title'] = "%s: <b>%s</b>" % (item[namekey], item['authors'][0])
        else:
            outitem['title'] = item[namekey]

        if 'abstract' in item:
            outitem['abstract'] = convert(item['abstract'])
        else:
            outitem['abstract'] = ''

        outitem['guid'] = hashlib.md5(outitem['conf_url']).hexdigest()

	outgoing_data[channel][(outitem['start'], outitem['end'])] = outitem

    # Fill in the breaks
    final_data = {}
    for channel in outgoing_data.keys():
        final_data[channel] = []
        channel_data = list(sorted(outgoing_data[channel].items()))

	newdata = {
	    'start': datetime.fromtimestamp(0, defaulttime.tzinfo),
	    'end': channel_data[0][0][0],
	    'title': '<i>Not Yet Started</i>',
	    'abstract': '',
	    }
        final_data[channel].append(newdata)

	end = channel_data[0][0][0]
        while len(channel_data) > 0:
            (start, _), data = channel_data.pop(0)

            if end.day != start.day:
                # Insert start / end time
                newdata = {
                    'start': end,
                    'end': end.replace(hour=23, minute=59, second=59),
                    'title': '<i>Finished for the day</i>',
                    'abstract': '',
                    'guid': hashlib.md5(str(end)+channel).hexdigest(),
                    }
                final_data[channel].append(newdata)

                newdata = {
                    'start': start.replace(hour=0, minute=0, second=0),
                    'end': start,
                    'title': '<i>Not yet started</i>',
                    'abstract': '',
                    'guid': hashlib.md5(str(start)+channel).hexdigest(),
                    }
                final_data[channel].append(newdata)


            delta = (start - end).seconds/60
            if delta and delta == 10:
                final_data[channel][-1]['end'] = final_data[channel][-1]['end']+timedelta(seconds=delta*60)
            elif delta:
                title = BREAK_NAMES.get(delta, 'Unknown %s' % delta)

                if title is not None:
                    if len(title) == 2:
                        title = title[start.hour >= 12]
                    newdata = {
                        'start': end,
                        'end': start,
                        'title': "<i>%s</i>" % title, 
                        'abstract': '',
                        'guid': hashlib.md5(str(start)+channel).hexdigest(),
                        }
                    final_data[channel].append(newdata)
            final_data[channel].append(data)
            end = data['end']

	newdata = {
	    'start': end,
            'end': end.replace(year=2100),
	    'title': '<i>Conference Finished :(</i>',
	    'abstract': '',
            'guid': hashlib.md5(str(end)+channel).hexdigest(),
	    }
        final_data[channel].append(newdata)

    for channel in final_data.keys():
        sys.stderr.write('\n%s\n' % channel)
        for value in final_data[channel]:
            value['start'] = str(value['start'])
            value['end'] = str(value['end'])
            sys.stderr.write("%s | %s | %s\n" % (value['start'], value['end'], value['title']))

    out = StringIO.StringIO()
    pprint.pprint(final_data, stream=out)
    print """\
import datetime
import pytz

data = \\"""
    print out.getvalue().replace("<DstTzInfo 'US/Pacific' PDT-1 day, 17:00:00 DST>", 'pytz.timezone("US/Pacific")')
