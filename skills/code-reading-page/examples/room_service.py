import asyncio
from dataclasses import dataclass, field
from typing import Optional

MAX_PLAYERS = 4  # 每間房的人數上限


@dataclass
class Room:
    """遊戲房間：記錄房號與目前的玩家。"""

    room_id: int
    players: list[str] = field(default_factory=list)
    locked: bool = False

    def join(self, player: str) -> bool:
        # 房間已鎖或人滿就拒絕
        if self.locked or len(self.players) >= MAX_PLAYERS:
            return False
        self.players.append(player)
        return True


class RoomService:
    def __init__(self, redis, ttl: int = 300):
        self.redis = redis
        self.ttl = ttl
        self._rooms: dict[int, Room] = {}

    async def find_room(self, room_id: int) -> Optional[Room]:
        if room_id in self._rooms:
            return self._rooms[room_id]
        raw = await self.redis.get(f"room:{room_id}")
        return None if raw is None else Room(room_id=room_id, players=raw.split(","))

    async def broadcast(self, room: Room, message: str) -> None:
        tasks = [self.redis.publish(f"player:{p}", message) for p in room.players]
        await asyncio.gather(*tasks)
