import os
from aiogram import F, types, Router
from aiogram.filters import CommandStart
from sqlalchemy.ext.asyncio import AsyncSession

from database.orm_query import (
    orm_add_to_cart,
    orm_add_user,
    orm_update_user_phone,
    orm_get_user_by_id,
    orm_get_user_carts  # Добавляем функцию для получения корзины
)

from filters.chat_types import ChatTypeFilter
from handlers.menu_processing import get_menu_content
from kbds.inline import MenuCallBack, get_callback_btns
from kbds.reply import create_contact_button

user_private_router = Router()
user_private_router.message.filter(ChatTypeFilter(["private"]))


@user_private_router.message(CommandStart())
async def start_cmd(message: types.Message, session: AsyncSession):
    media, reply_markup = await get_menu_content(session, level=0, menu_name="main")
    await message.answer_photo(media.media, caption=media.caption, reply_markup=reply_markup)


async def add_to_cart(callback: types.CallbackQuery, callback_data: MenuCallBack, session: AsyncSession):
    user = callback.from_user
    await orm_add_user(
        session,
        user_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=None,
    )
    await orm_add_to_cart(session, user_id=user.id, product_id=callback_data.product_id)
    await callback.answer("Товар добавлен в корзину.")


@user_private_router.callback_query(MenuCallBack.filter())
async def user_menu(callback: types.CallbackQuery, callback_data: MenuCallBack, session: AsyncSession):
    user_id = callback.from_user.id

    if callback_data.menu_name == "add_to_cart":
        await add_to_cart(callback, callback_data, session)
        return

    if callback_data.menu_name == "order":
        user = await orm_get_user_by_id(session, user_id)

        if user is None:
            await callback.message.answer("Пользователь не найден.")
            return
        
        if not user.phone:  # Упрощение условия
            contact_keyboard = create_contact_button()
            await callback.message.answer(f"Здравствуйте, {callback.from_user.full_name} 🌟")
            await callback.message.answer("Пожалуйста, отправьте ваш номер телефона:", reply_markup=contact_keyboard)
        else:
            await callback.message.answer(f"Здравствуйте, {callback.from_user.full_name} 🌟")
            await callback.message.answer(f"Мы рады снова видеть вас 🥳")
            # Здесь отправляем инвойс, так как номер телефона уже есть
            await send_invoice(callback.message, user_id, session)  # Изменено на callback.message

        await callback.answer()
        return

    media, reply_markup = await get_menu_content(
        session,
        level=callback_data.level,
        menu_name=callback_data.menu_name,
        category=callback_data.category,
        page=callback_data.page,
        product_id=callback_data.product_id,
        user_id=user_id,
    )

    await callback.message.edit_media(media=media, reply_markup=reply_markup)
    await callback.answer()


@user_private_router.message(F.contact)
async def handle_contact(message: types.Message, session: AsyncSession):
    user_id = message.from_user.id
    phone = message.contact.phone_number

    # Обновляем номер телефона в базе данных
    await orm_update_user_phone(session, user_id, phone)

    # Отправляем сообщение об успешном обновлении номера
    await message.answer("Успешно добавлен номер! 🌟", reply_markup=types.ReplyKeyboardRemove())

    # После успешного получения номера телефона, можем отправить инвойс
    await send_invoice(message, user_id, session)  # Передаем сессию


async def send_invoice(message: types.Message, user_id: int, session: AsyncSession):
    # Получаем товары из корзины
    cart_items = await orm_get_user_carts(session, user_id)

    if not cart_items:
        await message.answer("Ваша корзина пуста. Пожалуйста, добавьте товары перед оформлением заказа.")
        return

    # Здесь указываем настройки инвойса
    title = "Fast-Food"
    
    # Формируем описание инвойса с товарами и их количеством
    description_lines = [f"{item.product.name} - {item.quantity} шт." for item in cart_items]
    description = "Подробности вашего заказа:\n" + "\n".join(description_lines)
    
    payload = f"order_{user_id}"  # Например, уникальный идентификатор заказа
    provider_token = os.getenv("PAYMENT")
    currency = "UZS"  # Укажите валюту как узбекский сум
    start_parameter = "test"
    
    # Формируем цены из товаров в корзине
    prices = []
    total_amount = 0

    for item in cart_items:
        price = types.LabeledPrice(label=item.product.name, amount=item.product.price * item.quantity * 100)  # Указываем цену в копейках
        prices.append(price)
        total_amount += item.product.price * item.quantity

    # Добавляем итоговую сумму
    total_price_label = types.LabeledPrice(label="Итого", amount=total_amount * 100)
    prices.append(total_price_label)

    await message.answer_invoice(
        title=title,
        description=description,
        payload=payload,
        provider_token=provider_token,
        currency=currency,
        prices=prices,
        start_parameter=start_parameter,
        photo_url="https://external-content.duckduckgo.com/iu/?u=https%3A%2F%2Ftse2.mm.bing.net%2Fth%3Fid%3DOIP.lTjJIvFKdi5sEVjtgHFM7QHaEc%26pid%3DApi&f=1&ipt=3b47e2335d7e65b45ea84635e4c065c5a999fb3b387af4fcf26411f1c055ecb6&ipo=images",  # URL изображения товара
        photo_width=450,  # Ширина изображения
        photo_height=300,  # Высота изображения
        need_name=True,
        need_phone_number=True,
        need_email=True,
        need_shipping_address=False,
        is_flexible=False
    )
