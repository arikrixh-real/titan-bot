import traceback

import pyttsx3
import speech_recognition as sr

from data.live_price import get_live_price


# =========================
# TITAN VOICE ENGINE
# =========================

engine = pyttsx3.init()
engine.setProperty("rate", 170)


def speak(text):
    print(f"\nTITAN: {text}")
    engine.say(text)
    engine.runAndWait()


def explain_error(place, error):
    error_type = type(error).__name__
    error_message = str(error)

    print("\n========== TITAN ERROR REPORT ==========")
    print(f"Location: {place}")
    print(f"Error Type: {error_type}")
    print(f"Error Message: {error_message}")
    print("Full Traceback:")
    print(traceback.format_exc())
    print("========================================\n")

    speak(f"Error detected in {place}. The issue is {error_type}. {error_message}")


def listen():
    recognizer = sr.Recognizer()

    try:
        with sr.Microphone() as source:
            print("\nListening...")
            recognizer.adjust_for_ambient_noise(source)
            audio = recognizer.listen(source)

        try:
            command = recognizer.recognize_google(audio)
            print(f"\nYOU: {command}")
            return command.lower()

        except Exception as e:
            print(f"Speech recognition issue: {e}")
            speak("I heard audio, but could not understand it clearly.")
            return ""

    except Exception as e:
        explain_error("microphone listener", e)
        return ""


def get_reliance_price_response():
    try:
        price = get_live_price("RELIANCE")

        if price:
            return f"Reliance current price is {price} rupees."

        return "Unable to fetch Reliance live price. Possible issue: Upstox token expired, missing token, internet issue, or instrument key problem."

    except Exception as e:
        explain_error("Reliance live price fetch", e)
        return "Reliance live price failed due to an internal error."


# =========================
# MAIN LOOP
# =========================

speak("TITAN assistant activated. Error explainer is active.")

while True:

    try:
        mode = input("\nType [voice/text/exit]: ").lower().strip()

        if mode == "exit":
            speak("Shutting down.")
            break

        if mode == "text":
            command = input("\nYOU: ").lower().strip()

        elif mode == "voice":
            command = listen()

        else:
            continue

        if command == "":
            continue

        if "hello" in command or "hi" in command:
            speak("Hello. TITAN systems are operational.")

        elif "market" in command:
            speak("Indian market sentiment currently neutral.")

        elif "reliance" in command:
            speak(get_reliance_price_response())

        elif "error" in command or "problem" in command or "issue" in command:
            speak("TITAN error explainer is active. If an error happens, I will print the exact issue and explain it.")

        elif "exit" in command or "stop" in command:
            speak("Shutting down.")
            break

        else:
            speak("Command received.")

    except KeyboardInterrupt:
        speak("Manual shutdown detected.")
        break

    except Exception as e:
        explain_error("main assistant loop", e)