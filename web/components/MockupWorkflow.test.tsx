import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MockupWorkflow, type MockupPhase } from "./MockupWorkflow";
import type {
  ClarifyingQuestion,
  CreativeDirection,
  FinalPromptResponse,
  ListingRole,
  MockupAnalyzeResponse,
  RefinedStrategy,
} from "@/lib/mockup-types";

const DIRECTIONS: CreativeDirection[] = [
  {
    id: "moody_collector",
    title: "Moody Collector Apartment",
    rationale: "Matches the dark cinematic mood.",
    environment: "realistic styled home interior",
    mood: "dramatic",
    presentation_style: "editorial",
    recommended: true,
  },
  {
    id: "clean_gallery",
    title: "Clean Gallery Wall",
    rationale: "A minimal backdrop.",
    environment: "white gallery wall",
    mood: "minimal",
    presentation_style: "clean product",
    recommended: false,
  },
];

const QUESTIONS: ClarifyingQuestion[] = [
  { key: "framing", question: "Framed or unframed?", options: ["Framed", "Unframed"] },
  { key: "setting", question: "Where is it displayed?", options: ["Studio", "Home interior"] },
];

const ANALYSIS: MockupAnalyzeResponse = {
  asset_analysis: {
    product_type: "movie poster",
    asset_category: "printable wall art",
    product_category: "poster",
    presentation_mode: "physical",
    orientation: "portrait",
    aspect_ratio: "2:3",
    visual_style: "cinematic neo-noir",
    mood: ["dramatic"],
    dominant_colors: ["#1A1A2E"],
    content_summary: "A moody central character.",
    composition_notes: "Centered.",
    audience: "Cinephiles.",
    target_customer: "Film decor enthusiasts.",
    physical_presentation_assumption: "Framed print.",
  },
  recommended_directions: DIRECTIONS,
  best_recommendation: {
    id: "moody_collector",
    title: "Moody Collector Apartment",
    message: "A darker cinematic direction is recommended because it matches the mood.",
  },
  clarification_needed: true,
  clarifying_questions: QUESTIONS,
  mockups: [],
};

const STRATEGY: RefinedStrategy = {
  direction: DIRECTIONS[0],
  category: "poster",
  listing_role: "hero",
  environment: "realistic styled home interior",
  lighting: "dramatic moody lighting",
  surface_or_frame: "slim black frame",
  camera: "50mm",
  composition: "centered hero",
  styling_notes: "sparse props",
  applied_answers: { framing: "Framed", setting: "Studio" },
  remaining_questions: [],
};

const FINAL_PROMPT: FinalPromptResponse = {
  direction: DIRECTIONS[0],
  listing_role: "hero",
  recommended_usage: "Etsy hero image / first listing image",
  final_prompt: "The artwork in a slim black frame on a studio wall, dramatic lighting.",
  negative_prompt: "watermark, changed typography",
  preservation_notes: ["Do not alter the artwork artwork itself."],
  preservation_clause: "PRESERVATION_CLAUSE",
};

function renderWorkflow(
  props: Partial<{
    phase: MockupPhase;
    analysis: MockupAnalyzeResponse | null;
    selectedDirectionId: string | null;
    answers: Record<string, string>;
    listingRole: ListingRole;
    strategy: RefinedStrategy | null;
    finalPrompt: FinalPromptResponse | null;
    error: string | null;
    onSelectDirection: (id: string) => void;
    onAnswer: (key: string, value: string) => void;
    onListingRole: (role: ListingRole) => void;
    onRefine: () => void;
    onGenerate: () => void;
    onReset: () => void;
  }> = {},
) {
  const handlers = {
    onSelectDirection: props.onSelectDirection ?? vi.fn(),
    onAnswer: props.onAnswer ?? vi.fn(),
    onListingRole: props.onListingRole ?? vi.fn(),
    onRefine: props.onRefine ?? vi.fn(),
    onGenerate: props.onGenerate ?? vi.fn(),
    onReset: props.onReset ?? vi.fn(),
  };

  const utils = render(
    <MockupWorkflow
      phase={props.phase ?? "analysis"}
      analysis={props.analysis ?? ANALYSIS}
      selectedDirectionId={props.selectedDirectionId ?? "moody_collector"}
      answers={props.answers ?? {}}
      listingRole={props.listingRole ?? "hero"}
      strategy={props.strategy ?? null}
      finalPrompt={props.finalPrompt ?? null}
      error={props.error ?? null}
      {...handlers}
    />,
  );

  return { ...handlers, ...utils };
}

describe("MockupWorkflow", () => {
  it("renders the recommended direction and marks it", () => {
    renderWorkflow();
    expect(screen.getByText("Moody Collector Apartment")).toBeInTheDocument();
    expect(screen.getByText("[recommended]")).toBeInTheDocument();
    expect(screen.getByText("Clean Gallery Wall")).toBeInTheDocument();
  });

  it("selecting a different direction calls onSelectDirection", async () => {
    const user = userEvent.setup();
    const { onSelectDirection } = renderWorkflow({ selectedDirectionId: "moody_collector" });

    await user.click(screen.getByTestId("direction-clean_gallery"));

    expect(onSelectDirection).toHaveBeenCalledWith("clean_gallery");
  });

  it("selecting a clarification answer calls onAnswer", async () => {
    const user = userEvent.setup();
    const { onAnswer } = renderWorkflow({ answers: {} });

    await user.click(screen.getByTestId("answer-framing-Framed"));

    expect(onAnswer).toHaveBeenCalledWith("framing", "Framed");
  });

  it("listing-role selection calls onListingRole", async () => {
    const user = userEvent.setup();
    const { onListingRole } = renderWorkflow();

    await user.click(screen.getByTestId("role-close_up"));

    expect(onListingRole).toHaveBeenCalledWith("close_up");
  });

  it("disables refine until all questions are answered", () => {
    const { onRefine } = renderWorkflow({ answers: { framing: "Framed" } });
    const refine = screen.getByTestId("mockup-refine");
    expect(refine).toBeDisabled();
    expect(onRefine).not.toHaveBeenCalled();
  });

  it("enables refine once all questions are answered", async () => {
    const user = userEvent.setup();
    const { onRefine } = renderWorkflow({
      answers: { framing: "Framed", setting: "Studio" },
    });
    const refine = screen.getByTestId("mockup-refine");
    expect(refine).toBeEnabled();

    await user.click(refine);
    expect(onRefine).toHaveBeenCalledOnce();
  });

  it("renders the refined strategy when a strategy is present", () => {
    renderWorkflow({ phase: "strategy", strategy: STRATEGY });
    expect(screen.getByText("realistic styled home interior")).toBeInTheDocument();
    expect(screen.getByText("slim black frame")).toBeInTheDocument();
    expect(screen.getByText("dramatic moody lighting")).toBeInTheDocument();
  });

  it("shows generate when the strategy has no remaining questions", () => {
    renderWorkflow({ phase: "strategy", strategy: STRATEGY });
    expect(screen.getByTestId("mockup-generate")).toBeInTheDocument();
  });

  it("renders the final prompt and copies it", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });

    renderWorkflow({ phase: "done", finalPrompt: FINAL_PROMPT });

    expect(
      screen.getByText("use as: Etsy hero image / first listing image"),
    ).toBeInTheDocument();

    await user.click(screen.getByTestId("mockup-copy"));
    expect(writeText).toHaveBeenCalledWith(FINAL_PROMPT.final_prompt);
    expect(screen.getByText("copied")).toBeInTheDocument();
  });

  it("renders an error message", () => {
    renderWorkflow({ phase: "error", analysis: null, error: "Upstream failed." });
    expect(screen.getByTestId("mockup-error")).toHaveTextContent("Upstream failed.");
  });
});
