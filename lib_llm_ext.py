import os, openai

OPENROUTER_CLIENT = openai.OpenAI(
    api_key=os.environ["OPENROUTER_API_KEY"],
    base_url="https://openrouter.ai/api/v1"
)

ASI_CLIENT = openai.OpenAI(
    api_key=os.environ["ASI_API_KEY"],
    base_url="https://inference.asicloud.cudos.org/v1"
)

ANTHROPIC_CLIENT = openai.OpenAI(
    api_key=os.environ["ANTHROPIC_API_KEY"],
    base_url="https://api.anthropic.com/v1/"
)

def _clean(text):
    return text.replace("_quote_", '"').replace("_apostrophe_", "'")

def _chat(client, model, content, max_tokens=6000):
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        max_tokens=max_tokens,
        extra_body={
            "enable_thinking": True,
            "thinking_budget": 6000
        }
    )
    return _clean(resp.choices[0].message.content)


def useOpenRouter(content):
    return _chat(
        client=OPENROUTER_CLIENT,
        model="z-ai/glm-5.1",  # replace with your OpenRouter model id
        content=content
    )

def useMiniMax(content):
    return _chat(
        client=ASI_CLIENT,
        model="minimax/minimax-m2.7", #"minimax/minimax-m2.7", #"asi1-mini",
        content=content
    )

def useClaude(content):
    return _chat(
        client=ANTHROPIC_CLIENT,
        model="claude-opus-4-6",
        content=content
    )

_embedding_model = None

def initLocalEmbedding():
    model_name="intfloat/e5-large-v2"
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer(model_name)
    return _embedding_model

def useLocalEmbedding(atom):
    global _embedding_model
    if _embedding_model is None:
        raise RuntimeError("Call initLocalEmbedding() first.")
    return _embedding_model.encode(
        atom,
        normalize_embeddings=True
    ).tolist()

import os
import base64
import tempfile
import subprocess
import yt_dlp
from datetime import datetime


EPISODES_DIR = "./repos/mettaclaw/memory/episodes"


def episode_image_path(ext="jpg"):
    os.makedirs(EPISODES_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return os.path.join(EPISODES_DIR, f"{ts}.{ext}")


def get_youtube_media_url(youtube_url):
    opts = {
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": False,
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            return info["url"]
    except Exception as e:
        raise RuntimeError(
            f"Could not resolve YouTube video URL. "
            f"The video may be unavailable, private, region-blocked, login-gated, "
            f"or blocked from this machine. Original error: {e}"
        )


def youtube_frame_to_data_url(youtube_url, seconds=0):
    img_path = episode_image_path("jpg")
    media_url = get_youtube_media_url(youtube_url)

    subprocess.check_call(
        [
            "ffmpeg",
            "-y",
            "-ss", str(seconds),
            "-i", media_url,
            "-frames:v", "1",
            "-q:v", "2",
            img_path,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    with open(img_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    return "data:image/jpeg;base64," + b64


def useClaudeYoutubeImage(content, youtube_url, seconds=0, max_tokens=6000):
    image_data_url = youtube_frame_to_data_url(youtube_url, seconds=seconds)

    resp = ANTHROPIC_CLIENT.chat.completions.create(
        model="claude-opus-4-6",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": content,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data_url,
                        },
                    },
                ],
            }
        ],
        max_tokens=max_tokens,
    )

    return _clean(resp.choices[0].message.content)

if __name__ == "__main__":
    answer = useClaudeYoutubeImage(
        "Do you see a boat?",
        "https://www.youtube.com/watch?v=CMn6xQXuSjI"
    )

    print(answer)
