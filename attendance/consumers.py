import json
from channels.generic.websocket import AsyncWebsocketConsumer


class AttendanceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = "attendance_group"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        print("WS CONNECTED:", self.channel_name)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        print("WS DISCONNECTED:", self.channel_name)

    async def send_attendance(self, event):
        print("WS SEND_ATTENDANCE CALLED")
        print("EVENT DATA:", event.get("data"))

        await self.send(text_data=json.dumps(event["data"]))