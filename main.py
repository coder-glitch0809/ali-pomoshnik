"""Ali yordamchisini ishga tushirish.

    python main.py            # matn rejimi
    python main.py --speak    # matn rejimi + ovozli javob
    python main.py --voice    # to'liq ovozli rejim (uyg'otish so'zi bilan)
"""
import argparse
import logging
import sys

import anthropic

from ali import scheduler
from ali.brain import Brain
from ali.config import config
from ali.memory import memory

CYAN, GRAY, RESET = "\033[96m", "\033[90m", "\033[0m"


def setup_logging() -> None:
    logging.basicConfig(
        filename=config.log_path,
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        encoding="utf-8",
    )


def ask_safely(brain: Brain, text: str, on_text=None) -> str | None:
    def on_event(kind, data):
        if kind == "text" and on_text:
            on_text(data)
        elif kind == "tool_start" and on_text:
            on_text(f"{GRAY}[{data['name']}]{CYAN} ")

    try:
        return brain.ask(text, on_event=on_event)
    except anthropic.AuthenticationError:
        print("\n[!] API kaliti noto'g'ri yoki yo'q. .env faylida ANTHROPIC_API_KEY ni tekshiring.")
    except anthropic.RateLimitError:
        print("\n[!] So'rovlar chegarasi. Biroz kuting.")
    except anthropic.APIConnectionError:
        print("\n[!] Internetga ulanib bo'lmadi.")
    except anthropic.APIStatusError as e:
        print(f"\n[!] API xatosi {e.status_code}: {e.message}")
    return None


def run_text(speak: bool) -> None:
    speaker = None
    if speak:
        from ali.voice.speaker import Speaker
        speaker = Speaker()

    def confirm(name, args) -> bool:
        return input(f"\n{GRAY}[?] {name}({args}) bajarilsinmi? (ha/yo'q): {RESET}").strip().lower() in ("ha", "h", "y", "yes")

    def notify(msg: str) -> None:
        print(f"\n{CYAN}{config.assistant_name}: {msg}{RESET}")
        if speaker:
            speaker.say(msg)

    brain = Brain(confirm=confirm)
    scheduler.start(notify)
    print(f"{CYAN}{config.assistant_name} tayyor, {config.user_name}.{RESET}  "
          f"{GRAY}(/new - yangi suhbat, /facts - xotira, /exit - chiqish){RESET}")

    while True:
        try:
            text = input("\nSiz: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text in ("/exit", "/quit", "chiqish"):
            break
        if text == "/new":
            brain.new_session()
            print(f"{GRAY}Yangi suhbat boshlandi.{RESET}")
            continue
        if text == "/facts":
            print(memory.all_facts() or "Xotira bo'sh")
            continue

        print(f"{CYAN}{config.assistant_name}: ", end="", flush=True)
        answer = ask_safely(brain, text, on_text=lambda t: print(t, end="", flush=True))
        print(RESET)
        if answer and speaker:
            speaker.say(answer)
    print(f"{CYAN}Xayr, {config.user_name}.{RESET}")


def run_voice() -> None:
    from ali.voice.listener import Listener, strip_wake_word
    from ali.voice.speaker import Speaker

    speaker = Speaker()
    print("Mikrofon sozlanmoqda...")
    listener = Listener()

    def confirm(name, args) -> bool:
        speaker.say(f"{name} amalini bajaraymi?")
        reply = (listener.listen(timeout=6) or "").lower()
        return any(w in reply for w in ("ha", "xa", "bajar", "yes", "да"))

    def notify(msg: str) -> None:
        print(f"{CYAN}{config.assistant_name}: {msg}{RESET}")
        speaker.say(msg)

    brain = Brain(confirm=confirm)
    scheduler.start(notify)
    print(f"{CYAN}Tinglayapman. Chaqirish: {', '.join(config.wake_words)}{RESET}  {GRAY}(Ctrl+C - chiqish){RESET}")
    speaker.say(f"{config.assistant_name} tayyor, {config.user_name}.")

    in_conversation = False  # javobdan keyin bir muddat uyg'otish so'zisiz tinglaydi
    while True:
        heard = listener.listen(timeout=8 if in_conversation else None)
        if not heard:
            in_conversation = False
            continue
        print(f"{GRAY}Eshitildi: {heard}{RESET}")

        command = heard if in_conversation else strip_wake_word(heard)
        if command is None:
            continue
        if command == "":
            speaker.say(f"Ha, {config.user_name}?")
            command = listener.listen(timeout=8)
            if not command:
                continue
            print(f"{GRAY}Buyruq: {command}{RESET}")

        answer = ask_safely(brain, command)
        if answer:
            print(f"{CYAN}{config.assistant_name}: {answer}{RESET}")
            speaker.say(answer)
        in_conversation = True


def main() -> None:
    parser = argparse.ArgumentParser(description=f"{config.assistant_name} - shaxsiy yordamchi")
    parser.add_argument("--voice", action="store_true", help="to'liq ovozli rejim")
    parser.add_argument("--speak", action="store_true", help="matn rejimida javoblarni ovoz chiqarib o'qish")
    args = parser.parse_args()

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    setup_logging()

    try:
        run_voice() if args.voice else run_text(args.speak)
    except KeyboardInterrupt:
        print(f"\n{CYAN}Xayr, {config.user_name}.{RESET}")


if __name__ == "__main__":
    main()
