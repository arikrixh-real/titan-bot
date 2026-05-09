import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="TITAN", page_icon="●", layout="wide")

st.markdown("""
<style>
header, footer, #MainMenu {display:none!important;}
.stApp {background:#000!important;}
.block-container {padding:0!important; max-width:100%!important;}
</style>
""", unsafe_allow_html=True)

components.html("""
<!DOCTYPE html>
<html>
<head>
<style>
html, body {
    margin: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
    background: #000;
    font-family: Arial, sans-serif;
    color: white;
}

#stars {
    position: fixed;
    inset: 0;
    z-index: 0;
}

.main {
    position: relative;
    z-index: 2;
    height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
}

.title {
    margin-top: 58px;
    font-size: 26px;
    letter-spacing: 18px;
    font-weight: 300;
    color: rgba(255,255,255,.9);
}

.orb-wrap {
    margin-top: 65px;
}

.orb {
    width: 330px;
    height: 330px;
    filter: drop-shadow(0 0 32px rgba(0,220,255,.35));
}

.inside { transform-origin:300px 300px; animation: move1 15s ease-in-out infinite; }
.inside2 { transform-origin:300px 300px; animation: move2 22s ease-in-out infinite; }
.pulse { transform-origin:300px 300px; animation: pulse 3s ease-in-out infinite; }

.listening .orb {
    filter: drop-shadow(0 0 45px rgba(0,245,255,.75))
            drop-shadow(0 0 75px rgba(180,50,255,.35));
}

.listening .pulse { animation: voicePulse .75s ease-in-out infinite; }
.speaking .pulse { animation: voicePulse .45s ease-in-out infinite; }

@keyframes move1 {
    0% { transform: rotate(0deg) scale(1); }
    25% { transform: rotate(18deg) scale(1.05); }
    50% { transform: rotate(-12deg) scale(.98); }
    75% { transform: rotate(28deg) scale(1.04); }
    100% { transform: rotate(0deg) scale(1); }
}

@keyframes move2 {
    0% { transform: rotate(0deg); }
    35% { transform: rotate(-38deg); }
    70% { transform: rotate(25deg); }
    100% { transform: rotate(0deg); }
}

@keyframes pulse {
    0%,100% { transform:scale(.94); opacity:.86; }
    50% { transform:scale(1.08); opacity:1; }
}

@keyframes voicePulse {
    0%,100% { transform:scale(.88); opacity:.75; }
    50% { transform:scale(1.25); opacity:1; }
}

.greeting {
    margin-top: 30px;
    font-size: 26px;
    font-weight: 300;
    color: rgba(255,255,255,.92);
    text-align: center;
    min-height: 34px;
}

.bottom {
    position: fixed;
    bottom: 42px;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: 18px;
    z-index: 10;
}

.icon {
    width: 66px;
    height: 66px;
    border-radius: 50%;
    background: rgba(0,0,0,.72);
    border: 1px solid rgba(255,255,255,.24);
    color: white;
    font-size: 24px;
    cursor: pointer;
    box-shadow: 0 0 22px rgba(0,255,255,.18);
}

.icon:hover {
    border-color: rgba(0,245,255,.75);
    box-shadow: 0 0 34px rgba(0,245,255,.35);
}

.input-wrap {
    width: 760px;
    height: 66px;
    border-radius: 999px;
    background: rgba(3,3,4,.74);
    border: 1px solid rgba(255,255,255,.22);
    display: flex;
    align-items: center;
    box-shadow: 0 0 24px rgba(0,255,255,.13);
}

#msg {
    flex: 1;
    height: 100%;
    background: transparent;
    border: none;
    outline: none;
    color: white;
    font-size: 21px;
    padding-left: 30px;
}

.send {
    margin-right: 10px;
    width: 48px;
    height: 48px;
    border-radius: 50%;
    border: none;
    background: rgba(255,255,255,.13);
    color: white;
    font-size: 22px;
    cursor: pointer;
}
</style>
</head>

<body>
<canvas id="stars"></canvas>

<div class="main" id="main">
    <div class="title">TITAN</div>

    <div class="orb-wrap">
        <svg class="orb" viewBox="0 0 600 600">
            <defs>
                <radialGradient id="glass" cx="36%" cy="25%" r="78%">
                    <stop offset="0%" stop-color="white" stop-opacity=".32"/>
                    <stop offset="20%" stop-color="#7df7ff" stop-opacity=".12"/>
                    <stop offset="55%" stop-color="#11152f" stop-opacity=".42"/>
                    <stop offset="76%" stop-color="#03040a" stop-opacity=".80"/>
                    <stop offset="100%" stop-color="#000" stop-opacity=".98"/>
                </radialGradient>

                <radialGradient id="rim" cx="50%" cy="50%" r="50%">
                    <stop offset="70%" stop-color="transparent"/>
                    <stop offset="86%" stop-color="#00eaff" stop-opacity=".42"/>
                    <stop offset="95%" stop-color="#af4cff" stop-opacity=".62"/>
                    <stop offset="100%" stop-color="white" stop-opacity=".18"/>
                </radialGradient>

                <clipPath id="clip"><circle cx="300" cy="300" r="170"/></clipPath>
                <filter id="blur"><feGaussianBlur stdDeviation="13"/></filter>
                <filter id="glow" x="-70%" y="-70%" width="240%" height="240%">
                    <feGaussianBlur stdDeviation="9" result="b"/>
                    <feMerge>
                        <feMergeNode in="b"/>
                        <feMergeNode in="SourceGraphic"/>
                    </feMerge>
                </filter>
            </defs>

            <circle cx="300" cy="300" r="170" fill="url(#glass)"/>
            <circle cx="300" cy="300" r="173" fill="url(#rim)"/>
            <circle cx="300" cy="300" r="171" fill="none" stroke="rgba(255,255,255,.09)" stroke-width="1.4"/>

            <g clip-path="url(#clip)">
                <g class="inside" filter="url(#blur)">
                    <ellipse cx="238" cy="320" rx="92" ry="80" fill="#ff135e" opacity=".78"/>
                    <ellipse cx="248" cy="246" rx="82" ry="120" fill="#00eaff" opacity=".72" transform="rotate(-28 248 246)"/>
                    <ellipse cx="360" cy="285" rx="98" ry="72" fill="#00cfff" opacity=".52"/>
                    <ellipse cx="320" cy="230" rx="82" ry="112" fill="#ac42ff" opacity=".56" transform="rotate(18 320 230)"/>
                </g>

                <g class="inside2" filter="url(#glow)">
                    <path d="M300 300 C155 240,215 176,300 232 C395 292,426 334,300 300Z" fill="#00f6ff" opacity=".46"/>
                    <path d="M300 300 C438 210,420 350,300 340 C205 333,170 285,300 300Z" fill="#8a45ff" opacity=".42"/>
                    <path d="M300 300 C205 410,180 286,300 255 C388 230,410 260,300 300Z" fill="#ff0b77" opacity=".42"/>
                </g>

                <ellipse class="pulse" cx="300" cy="300" rx="92" ry="56" fill="white" opacity=".92" filter="url(#glow)"/>
            </g>

            <circle cx="246" cy="205" r="22" fill="white" opacity=".50" filter="url(#glow)"/>
        </svg>
    </div>

    <div class="greeting" id="reply">Hi.</div>
</div>

<div class="bottom">
    <button class="icon" onclick="setReply('Chat mode active.')">💬</button>

    <div class="input-wrap">
        <input id="msg" placeholder="Message TITAN..." />
        <button class="send" onclick="sendMsg()">↑</button>
    </div>

    <button class="icon" onclick="startVoice()">🎙</button>
    <button class="icon" onclick="clearMsg()">🧹</button>
</div>

<script>
const canvas = document.getElementById("stars");
const ctx = canvas.getContext("2d");
const main = document.getElementById("main");

function resize() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
}
resize();
window.addEventListener("resize", resize);

const stars = [];

for (let i = 0; i < 850; i++) {
    stars.push({
        x: Math.random() * window.innerWidth,
        y: Math.random() * window.innerHeight,
        r: Math.random() * 1.4 + 0.2,
        a: Math.random() * 0.45 + 0.05,
        blue: Math.random() > 0.88
    });
}

function drawStars() {
    ctx.clearRect(0,0,canvas.width,canvas.height);

    for (const s of stars) {
        ctx.beginPath();

        ctx.fillStyle = s.blue
            ? `rgba(90,190,255,${s.a})`
            : `rgba(255,255,255,${s.a})`;

        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fill();
    }
}

drawStars();

function setReply(text) {
    document.getElementById("reply").innerText = text;
}

async function titanBrain(text) {
    await new Promise(resolve => setTimeout(resolve, 500));

    const lower = text.toLowerCase();

    if (lower.includes("hello") || lower.includes("hi")) {
        return "Hello. TITAN assistant is online.";
    }

    if (lower.includes("status")) {
        return "TITAN assistant website is online. Core trading bot remains separate and untouched.";
    }

    if (lower.includes("backend")) {
        return "Online backend is not connected yet. Website mode is active.";
    }

    if (lower.includes("reliance") || lower.includes("price")) {
        return "Live price backend is not connected yet. Next step is connecting Supabase or TITAN API safely.";
    }

    if (lower.includes("market")) {
        return "Market intelligence display is ready. Live market data connection will be added safely next.";
    }

    if (lower.includes("trade") || lower.includes("trades")) {
        return "Live trades connection is not added yet. The assistant UI is online and ready for safe integration.";
    }

    if (lower.includes("error")) {
        return "No website crash detected. Backend integration is pending.";
    }

    if (lower.includes("voice")) {
        return "Voice mode is active if your browser allows microphone and speech permissions.";
    }

    return "TITAN received: " + text;
}

function speak(text) {
    if (!("speechSynthesis" in window)) {
        setReply(text);
        return;
    }

    window.speechSynthesis.cancel();

    const utter = new SpeechSynthesisUtterance(text);
    utter.rate = 0.95;
    utter.pitch = 0.9;
    utter.volume = 1;

    utter.onstart = () => {
        main.classList.remove("listening");
        main.classList.add("speaking");
    };

    utter.onend = () => {
        main.classList.remove("speaking");
    };

    window.speechSynthesis.speak(utter);
}

async function processMessage(text) {
    if (!text.trim()) return;

    setReply("Thinking...");

    const reply = await titanBrain(text);

    setReply(reply);

    speak(reply);
}

function sendMsg() {
    const input = document.getElementById("msg");
    const text = input.value.trim();
    if (!text) return;

    processMessage(text);
    input.value = "";
}

function clearMsg() {
    document.getElementById("msg").value = "";
    setReply("Hi.");
    if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
    }
    main.classList.remove("listening");
    main.classList.remove("speaking");
}

function startVoice() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
        setReply("Voice is not supported in this browser. Use Chrome.");
        speak("Voice is not supported in this browser. Use Chrome.");
        return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "en-IN";
    recognition.interimResults = false;
    recognition.continuous = false;

    recognition.onstart = () => {
        main.classList.add("listening");
        setReply("Listening...");
    };

    recognition.onresult = (event) => {
        const text = event.results[0][0].transcript;
        setReply("You said: " + text);
        processMessage(text);
    };

    recognition.onerror = (event) => {
        main.classList.remove("listening");
        const errorText = "Voice error: " + event.error;
        setReply(errorText);
        speak(errorText);
    };

    recognition.onend = () => {
        main.classList.remove("listening");
    };

    recognition.start();
}

document.getElementById("msg").addEventListener("keydown", function(e) {
    if (e.key === "Enter") sendMsg();
});
</script>
</body>
</html>
""", height=900, scrolling=False)