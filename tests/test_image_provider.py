import base64
from types import SimpleNamespace

from src.image_provider import OpenAIImageProvider


class _FakeOpenAIImagesClient:
    def __init__(self, b64_png: str):
        self.images = SimpleNamespace(generate=self._generate)
        self._b64_png = b64_png
        self.captured_kwargs = None

    def _generate(self, **kwargs):
        self.captured_kwargs = kwargs
        return SimpleNamespace(data=[SimpleNamespace(b64_json=self._b64_png)])


def test_generate_image_returns_decoded_bytes():
    raw = b"fake-png-bytes"
    client = _FakeOpenAIImagesClient(base64.b64encode(raw).decode("ascii"))
    provider = OpenAIImageProvider(client=client)

    result = provider.generate_image("A latte with micro-foam art.")

    assert result == raw
    assert client.captured_kwargs["prompt"] == "A latte with micro-foam art."
    assert client.captured_kwargs["size"] == "1024x1024"


def test_generate_image_passes_custom_size():
    raw = b"x"
    client = _FakeOpenAIImagesClient(base64.b64encode(raw).decode("ascii"))
    provider = OpenAIImageProvider(client=client)

    provider.generate_image("A cafe interior.", size="512x512")

    assert client.captured_kwargs["size"] == "512x512"
