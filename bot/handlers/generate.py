@generate_router.callback_query(F.data == "gen:detail")
async def gen_ask_detail(cb: CallbackQuery, state: FSMContext):
    st = await _check_result_session(cb, state)
    if st is None:
        return
    
    # Режим доработки существующего изображения (In-painting)
    st["edit_mode"] = True
    # Фиксируем ID текущей генерации, чтобы использовать его как reference_image
    st["edit_base_id"] = st.get("last_generation_id")
    # Не сбрасываем seed и прошлые настройки!
    await state.set_data(st)
    await state.set_state(GenerateState.asking_detail)
    await cb.answer()
    
    # Показываем клавиатуру с кнопкой "◀️ Назад"
    await cb.message.answer(
        texts.ASK_DETAIL,
        reply_markup=get_back_keyboard()
    )


@generate_router.message(GenerateState.asking_detail, F.text)
async def gen_handle_detail(msg: Message, state: FSMContext, session: AsyncSession):
    text = msg.text.strip()
    if text == texts.BTN_BACK or text == texts.BTN_CANCEL:
        await state.set_state(GenerateState.viewing_result)
        await msg.answer(texts.BACK_TO_RESULT, reply_markup=get_result_keyboard())
        return

    if len(text) > 100:
        await msg.answer(texts.DETAIL_TOO_LONG)
        return

    st = await state.get_data()
    
    # Сохраняем введенную деталь в сессию, сохраняя предыдущие контексты
    st["custom_detail"] = text
    await state.set_data(st)
    
    # Запускаем генерацию с учётом сохранённого edit_base_id и seed
    await run_generation_pipeline(msg, state, session)