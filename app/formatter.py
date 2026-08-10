def build_message(original_text: str, source_title: str, translated_text: str) -> str:
    return (
        f"מקור: {source_title}\n\n"
        f"{translated_text}\n\n"
        f"────────────────────\n\n"
        f"🇸🇦 מקור\n\n"
        f"{original_text}"
    )
