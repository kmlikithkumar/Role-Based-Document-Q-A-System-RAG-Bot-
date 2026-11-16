"""Fake Gemini API (generateContent / streamGenerateContent): checks the API key and the rules the real API enforces.
   python fake_gemini.py PORT LOGFILE [MODE]      MODE: quota | badkey | nomodel"""
import asyncio, json, sys

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

PORT, LOG = int(sys.argv[1]), sys.argv[2]
MODE = sys.argv[3] if len(sys.argv) > 3 else ""
app = FastAPI()


def err(code, status, message):
    return JSONResponse({"error": {"code": code, "message": message, "status": status}}, status_code=code)


@app.post("/{ver}/models/{target}")
async def generate(ver: str, target: str, req: Request):
    model, _, action = target.partition(":")
    body, key = await req.json(), req.headers.get("x-goog-api-key")
    open(LOG, "a").write(json.dumps({"model": model, "stream": action == "streamGenerateContent", "key": key, **body}) + "\n")
    if key != "test-key" or MODE == "badkey":
        return err(400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key.")
    if MODE == "quota":
        return err(429, "RESOURCE_EXHAUSTED", "You exceeded your current quota, please check your plan and billing details.")
    if MODE == "nomodel":
        return err(404, "NOT_FOUND", f"models/{model} is not found for API version v1beta, or is not supported for generateContent.")
    roles = [c.get("role") for c in body.get("contents", [])]
    if not roles or roles[0] != "user" or roles[-1] != "user" or any(a == b for a, b in zip(roles, roles[1:])):
        return err(400, "INVALID_ARGUMENT", "Please ensure that multiturn requests alternate between user and model, starting and ending with user.")
    if {"temperature", "topP", "topK"} & set(body.get("generationConfig", {})):
        return err(400, "INVALID_ARGUMENT", "temperature, top_p and top_k are no longer supported for this model.")
    usage = {"promptTokenCount": 1, "candidatesTokenCount": 4, "totalTokenCount": 5}
    if action != "streamGenerateContent":
        return {"candidates": [{"content": {"role": "model", "parts": [{"text": "annual leave days"}]}, "finishReason": "STOP", "index": 0}], "usageMetadata": usage, "modelVersion": model}

    async def gen():
        words = ["Answer ", "from ", "context ", "[1]."]
        for i, w in enumerate(words):
            chunk = {"candidates": [{"content": {"role": "model", "parts": [{"text": w}]}, "index": 0, **({"finishReason": "STOP"} if i == len(words) - 1 else {})}],
                     "modelVersion": model, **({"usageMetadata": usage} if i == len(words) - 1 else {})}
            yield f"data: {json.dumps(chunk)}\r\n\r\n"
            await asyncio.sleep(0.3)

    return StreamingResponse(gen(), media_type="text/event-stream")


uvicorn.run(app, port=PORT, log_level="warning")
