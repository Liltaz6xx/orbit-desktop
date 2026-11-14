# Third-party software and models

ORBIT installs Python packages through pip. Model weights are downloaded separately by users.

| Component | Use in ORBIT | Upstream terms |
| --- | --- | --- |
| Qwen2.5 1.5B | Default local Ollama model, installed with `ollama pull qwen2.5:1.5b` | [Apache 2.0 in Ollama's model listing](https://ollama.com/library/qwen2.5:1.5b) |
| Qwen2.5 3B | Optional model selection | [Qwen Research License](https://ollama.com/library/qwen2.5:3b/blobs/b5c0e5cf74cf) |
| Kokoro 82M | Neural text-to-speech weights and `bm_george` voice | [Kokoro model card and Apache 2.0 licence](https://huggingface.co/hexgrad/Kokoro-82M) |
| kokoro-onnx | ONNX inference interface and model exports | [MIT library licence and model terms](https://github.com/thewh1teagle/kokoro-onnx#license) |
| PySide6 Essentials | Qt desktop interface | [Qt for Python licensing](https://doc.qt.io/qtforpython-6/licenses.html) |

Setup can fetch `kokoro-v1.0.int8.onnx` and `voices-v1.0.bin` after you opt in. The downloader verifies each file against its expected SHA-256 hash. [Kokoro ONNX voice assets](https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.1)

Every separately installed model or library remains subject to its upstream terms.

The Windows installer uses [uv](https://docs.astral.sh/uv/reference/policies/license/) to install verified Python wheels into a private environment. It downloads the [CPython distribution from Python Build Standalone](https://github.com/astral-sh/python-build-standalone). Those packages retain their upstream licence files.
