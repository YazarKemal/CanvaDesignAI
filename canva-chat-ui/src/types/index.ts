export interface PromptCardData {
  aspectRatio: string;
  targetTool: string;
  promptText: string;
  canvaTip: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  promptCard?: PromptCardData;
  timestamp: number;
}
