async def prepare_runware_payload(
    prompt: str,
    reference_image_url: str | None,
    seed: int | None,
    is_edit_mode: bool = False
) -> dict:
    """Формирует payload для Runware API с фиксацией единого разрешения и параметров."""
    
    payload = {
        "positivePrompt": prompt,
        # Зафиксированное единое разрешение 1024x1536 (высокое качество 2:3)
        "width": 1024,
        "height": 1536,
        "steps": 30,
        "CFGScale": 7.0,
        "numberResults": 1,
        "outputFormat": "WEBP",
    }
    
    # Если зафиксирован seed — передаём его для точности воспроизведения
    if seed is not None:
        payload["seed"] = seed
        
    # В режиме редактирования детали передаём исходный кадр
    if is_edit_mode and reference_image_url:
        payload["seedImage"] = reference_image_url
        payload["strength"] = 0.45  # Сохраняет 55% исходного кадра (позу, лица) и меняет только детали
        
    return payload