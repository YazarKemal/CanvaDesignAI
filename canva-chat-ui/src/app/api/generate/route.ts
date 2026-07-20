import { NextResponse } from "next/server";

interface PromptCardData {
  aspectRatio: string;
  targetTool: string;
  promptText: string;
  canvaTip: string;
}

// Sample response templates that simulate what DeepSeek/Claude would return
const MOCK_RESPONSES: Array<{
  message: string;
  promptCard: PromptCardData;
}> = [
  {
    message:
      "İşte **Instagram gönderisi** için optimize edilmiş bir Canva prompt'u hazırladım. Bu prompt'u doğrudan Magic Media'ya yapıştırabilirsin.",
    promptCard: {
      aspectRatio: "1:1",
      targetTool: "Magic Media",
      promptText:
        "Minimalist modern office workspace with warm ambient lighting, floating holographic UI panels displaying analytics dashboards, soft bokeh background with blue and purple gradient, photorealistic 8K render, clean composition, professional tech aesthetic, shallow depth of field",
      canvaTip:
        "Bu prompt'u Magic Media'da kullandıktan sonra, Canva'nın 'Adjust' aracıyla renk sıcaklığını hafifçe artırarak daha sıcak bir ton elde edebilirsin. Ayrıca 'Background Remover' ile arka planı temizleyip kendi marka rengini ekleyebilirsin.",
    },
  },
  {
    message:
      "İşte **YouTube thumbnail** için dikkat çekici bir Canva prompt'u hazırladım. Bu tasarım tıklanma oranını artıracak.",
    promptCard: {
      aspectRatio: "16:9",
      targetTool: "Text to Image",
      promptText:
        "Dramatic cinematic portrait of a futuristic AI robot hand reaching out to touch glowing digital data streams, neon blue and magenta color scheme, dark gradient background with circuit board patterns, extreme detail, professional thumbnail composition, bold visual impact, 4K quality",
      canvaTip:
        "Bu görseli oluşturduktan sonra, Canva'da üzerine kalın bir 'Impact' fontuyla başlık ekle. Metnin okunabilirliği için görselin üst kısmına %40 opaklıkta siyah bir gradient overlay yerleştir.",
    },
  },
  {
    message:
      "İşte **TikTok/Reels** dikey videosu için optimize edilmiş bir prompt hazırladım.",
    promptCard: {
      aspectRatio: "9:16",
      targetTool: "AI Video",
      promptText:
        "Cinematic vertical video of a time-lapse sunrise over a futuristic smart city skyline, flying electric vehicles leaving light trails, holographic billboards displaying dynamic art, golden hour color palette transitioning to neon night, smooth camera pan upward, 60fps, trending social media aesthetic",
      canvaTip:
        "AI Video çıktısını aldıktan sonra, Canva'nın 'Beat Sync' özelliğiyle görüntüyü trend bir müzik parçasına senkronize et. Ayrıca üst ve alt kısımlara blur efekti verilmiş kopya katmanlar ekleyerek profesyonel bir letterbox efekti oluştur.",
    },
  },
  {
    message:
      "İşte **sunum kapağı** için profesyonel bir Canva prompt'u hazırladım.",
    promptCard: {
      aspectRatio: "16:9",
      targetTool: "AI Presentation",
      promptText:
        "Professional presentation slide background with abstract geometric shapes in gradient indigo and teal tones, subtle glassmorphism overlapping translucent circles, clean corporate minimal style, dark mode aesthetic, centered composition with ample negative space for text overlay, 4K resolution",
      canvaTip:
        "Bu arka planı Canva'da slayt arka planı olarak kullan. Metinlerini 'Montserrat' veya 'Poppins' fontuyla beyaz renkte ekle. Görselin sol tarafına %30 opaklıkta koyu bir overlay ekleyerek metin okunabilirliğini artırabilirsin.",
    },
  },
  {
    message:
      "İşte **ürün tanıtımı** için etkileyici bir Canva prompt'u.",
    promptCard: {
      aspectRatio: "1:1",
      targetTool: "AI Photo",
      promptText:
        "Product photography style image of a sleek minimalist smartwatch floating above a reflective dark surface, surrounded by ethereal light particles and subtle fog, premium luxury aesthetic, angular dramatic lighting from top left creating long shadows, monochromatic black and silver color scheme with accent gold highlights, 8K commercial quality",
      canvaTip:
        "AI Photo çıktısını Canva'da 'Magic Eraser' ile arka planı temizle, ardından markanın renk paletine uygun yeni bir degrade arka plan ekle. 'Shadows' efektini kullanarak ürünün altına yumuşak bir gölge eklemeyi unutma.",
    },
  },
];

// Simple mock delay to simulate API latency
function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function POST(request: Request) {
  try {
    const { prompt: userPrompt } = await request.json();

    if (!userPrompt || typeof userPrompt !== "string") {
      return NextResponse.json(
        { error: "Prompt is required and must be a string" },
        { status: 400 }
      );
    }

    // Simulate processing delay (800-1500ms)
    await delay(800 + Math.random() * 700);

    // Pick a response deterministically-ish based on prompt content
    const lower = userPrompt.toLowerCase();
    let index: number;

    if (lower.includes("instagram") || lower.includes("sosyal medya") || lower.includes("post")) {
      index = 0;
    } else if (lower.includes("youtube") || lower.includes("thumbnail") || lower.includes("küçük resim")) {
      index = 1;
    } else if (lower.includes("tiktok") || lower.includes("reels") || lower.includes("dikey") || lower.includes("video")) {
      index = 2;
    } else if (lower.includes("sunum") || lower.includes("presentation") || lower.includes("slayt")) {
      index = 3;
    } else if (lower.includes("ürün") || lower.includes("product") || lower.includes("fotoğraf")) {
      index = 4;
    } else {
      // Random fallback
      index = Math.floor(Math.random() * MOCK_RESPONSES.length);
    }

    return NextResponse.json(MOCK_RESPONSES[index]);
  } catch {
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
