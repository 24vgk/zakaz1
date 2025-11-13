from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser

from db import session_scope
from crud import get_or_create_user, ensure_bootstrap_admins
from config import BOOTSTRAP_ADMIN_IDS

class RoleMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # для callback_query user может отсутствовать в data — берём из event
        tg_user: TgUser | None = data.get("event_from_user") or getattr(event, "from_user", None)
        if tg_user is None:
            return await handler(event, data)

        async with session_scope() as s:
            if BOOTSTRAP_ADMIN_IDS:
                await ensure_bootstrap_admins(s, BOOTSTRAP_ADMIN_IDS)
            u = await get_or_create_user(
                s,
                tg_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
            )
            role = getattr(u.role, "value", str(u.role))

        data["event_from_user_role"] = role  # "admin" | "user"
        return await handler(event, data)
