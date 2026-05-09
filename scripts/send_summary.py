import json, urllib.request

phone = '62895621691627'
chat_id = f'{phone}@s.whatsapp.net'

message = """*Event Organizer Daily Summary*

*EVENTS TOMORROW (May 10):*

- Team standup meeting - 10:00 AM @ Room Alpha (Zoom)
  Everyone must prep their weekly report

- Budget approval DEADLINE - 5:00 PM
  Must submit to finance ASAP

*Upcoming:*
- Client presentation deadline - Monday May 11, 2:00 PM
  Need to finalize slides by Friday

*Pending Actions (TOMORROW):*
- [MEDIUM] Prepare weekly report (due: May 10, 10:00)
- [HIGH] Submit budget to finance ASAP (due: May 10, 17:00)

*Pending Actions (May 11):*
- [MEDIUM] Finalize slides for client presentation (due: May 11, 14:00)

WARNING: You have 2 HIGH/MEDIUM priority items due TOMORROW. Take action today!"""

payload = json.dumps({'chatId': chat_id, 'message': message}).encode()
req = urllib.request.Request(
    'http://localhost:3000/send',
    data=payload,
    headers={'Content-Type': 'application/json'},
    method='POST',
)
with urllib.request.urlopen(req, timeout=15) as resp:
    result = json.loads(resp.read())
    print('Result:', result)
