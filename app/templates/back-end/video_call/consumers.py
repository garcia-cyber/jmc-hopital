from channels.generic.websocket import AsyncJsonWebsocketConsumer


class VideoCallConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope["url_route"]["kwargs"]["room_name"]
        self.room_group_name = f"video_call_{self.room_name}"

        user = self.scope["user"]

        if not user.is_authenticated:
            await self.close(code=4401)
            return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive_json(self, content):
        message_type = content.get("type")

        if message_type not in ["offer", "answer", "ice-candidate", "user-joined"]:
            return

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "signal_message",
                "sender_id": self.scope["user"].id,
                "payload": content,
            }
        )

    async def signal_message(self, event):
        if event["sender_id"] == self.scope["user"].id:
            return

        await self.send_json(event["payload"])