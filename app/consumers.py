import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from .models import VideoRoom


class VideoCallConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope["url_route"]["kwargs"]["room_name"]
        self.room_group_name = f"video_call_{self.room_name}"
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            await self.close()
            return

        room = await sync_to_async(VideoRoom.objects.filter(name=self.room_name).first)()
        if not room:
            await self.close()
            return

        allowed = await sync_to_async(room.allowed_users.filter(id=self.user.id).exists)()
        if not allowed:
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        await self.send(text_data=json.dumps({
            "type": "system",
            "message": "connected",
            "user": self.user.username,
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        data = json.loads(text_data)
        event_type = data.get("type")

        if event_type == "offer":
            await self.channel_layer.group_send(self.room_group_name, {
                "type": "video.message",
                "message": {"type": "offer", "offer": data.get("offer")}
            })

        elif event_type == "answer":
            await self.channel_layer.group_send(self.room_group_name, {
                "type": "video.message",
                "message": {"type": "answer", "answer": data.get("answer")}
            })

        elif event_type == "candidate":
            await self.channel_layer.group_send(self.room_group_name, {
                "type": "video.message",
                "message": {"type": "candidate", "candidate": data.get("candidate")}
            })

        elif event_type == "hangup":
            await self.channel_layer.group_send(self.room_group_name, {
                "type": "video.message",
                "message": {"type": "hangup"}
            })

    async def video_message(self, event):
        await self.send(text_data=json.dumps(event["message"]))