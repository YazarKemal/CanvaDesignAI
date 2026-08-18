import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChatInput } from "./ChatInput";
import { MAX_IMAGE_BYTES, type AttachedImage } from "@/lib/mockup-types";

function renderInput(
  props: Partial<{
    value: string;
    suggestion: string;
    onSuggestionAccept: () => void;
    image: AttachedImage | null;
    onImageChange: (file: File | null) => void;
  }> = {},
) {
  const onChange = vi.fn();
  const onSubmit = vi.fn();
  const onHistoryPrev = vi.fn();
  const onSuggestionAccept = props.onSuggestionAccept ?? vi.fn();
  const onImageChange = props.onImageChange ?? vi.fn();

  const utils = render(
    <ChatInput
      value={props.value ?? ""}
      onChange={onChange}
      onSubmit={onSubmit}
      onHistoryPrev={onHistoryPrev}
      suggestion={props.suggestion}
      onSuggestionAccept={onSuggestionAccept}
      image={props.image ?? null}
      onImageChange={onImageChange}
    />,
  );

  const input = screen.getByRole("textbox") as HTMLInputElement;
  return { input, onChange, onSubmit, onHistoryPrev, onSuggestionAccept, onImageChange, ...utils };
}

describe("ChatInput ghost-text autosuggestion", () => {
  it("renders ghost text overlay when input is empty and suggestion is provided", () => {
    renderInput({ value: "", suggestion: "a test suggestion prompt" });

    const ghost = screen.getByText("a test suggestion prompt");
    expect(ghost).toBeInTheDocument();
    expect(ghost).toHaveClass("text-zinc-700");
    expect(ghost).toHaveAttribute("aria-hidden", "true");
  });

  it("hides ghost text when input has a value", () => {
    renderInput({ value: "hello world", suggestion: "a test suggestion" });

    expect(screen.queryByText("a test suggestion")).not.toBeInTheDocument();
  });

  it("hides ghost text when no suggestion is provided", () => {
    renderInput({ value: "", suggestion: undefined });

    // The input should show the default placeholder instead
    const input = screen.getByRole("textbox") as HTMLInputElement;
    expect(input.placeholder).toBe("a grand opening flyer for a specialty coffee shop");
  });

  it("ArrowRight fills suggestion when input is empty", async () => {
    const user = userEvent.setup();
    const { onChange, onSuggestionAccept, input } = renderInput({
      value: "",
      suggestion: "fill me in",
    });

    input.focus();
    await user.keyboard("{ArrowRight}");

    expect(onChange).toHaveBeenCalledWith("fill me in");
    expect(onSuggestionAccept).toHaveBeenCalledOnce();
  });

  it("ArrowRight does NOT trigger suggestion when input has content", async () => {
    const user = userEvent.setup();
    const { onChange, onSuggestionAccept, input } = renderInput({
      value: "already typed",
      suggestion: "do not use me",
    });

    input.focus();
    await user.keyboard("{ArrowRight}");

    // onChange should NOT be called with the suggestion
    const calls = onChange.mock.calls.map((c: string[]) => c[0]);
    expect(calls).not.toContain("do not use me");
    expect(onSuggestionAccept).not.toHaveBeenCalled();
  });

  it("Enter still submits (regression)", async () => {
    const user = userEvent.setup();
    const { onSubmit, input } = renderInput({ value: "hello", suggestion: "ignored" });

    input.focus();
    await user.keyboard("{Enter}");

    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it("ArrowUp still triggers history (regression)", async () => {
    const user = userEvent.setup();
    const { onHistoryPrev, input } = renderInput({ value: "", suggestion: "ignored" });

    input.focus();
    await user.keyboard("{ArrowUp}");

    expect(onHistoryPrev).toHaveBeenCalledOnce();
  });
});

describe("ChatInput image attachment", () => {
  it("submits text without an image (text-only regression)", async () => {
    const user = userEvent.setup();
    const { onSubmit, input } = renderInput({ value: "hello" });

    input.focus();
    await user.keyboard("{Enter}");

    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it("attaches a supported image file", async () => {
    const user = userEvent.setup();
    const { onImageChange } = renderInput();
    const file = new File(["poster"], "poster.png", { type: "image/png" });

    const fileInput = screen.getByTestId("mockup-image-input") as HTMLInputElement;
    await user.upload(fileInput, file);

    expect(onImageChange).toHaveBeenCalledWith(file);
  });

  it("rejects an unsupported file type and reports an error", () => {
    const { onImageChange } = renderInput();
    const file = new File(["x"], "notes.txt", { type: "text/plain" });

    // fireEvent bypasses userEvent's accept-attribute filtering so we can
    // exercise the component's own type validation (a real picker lets the
    // user choose "All files").
    const fileInput = screen.getByTestId("mockup-image-input") as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [file] } });

    expect(onImageChange).not.toHaveBeenCalled();
    expect(screen.getByTestId("mockup-image-error")).toHaveTextContent(
      "Unsupported file type",
    );
  });

  it("rejects a file larger than the 10 MB limit", async () => {
    const user = userEvent.setup();
    const { onImageChange } = renderInput();
    const big = new File([new Uint8Array(MAX_IMAGE_BYTES + 1)], "big.png", {
      type: "image/png",
    });

    const fileInput = screen.getByTestId("mockup-image-input") as HTMLInputElement;
    await user.upload(fileInput, big);

    expect(onImageChange).not.toHaveBeenCalled();
    expect(screen.getByTestId("mockup-image-error")).toHaveTextContent("10 MB");
  });

  it("shows the attached image filename and clears it", async () => {
    const user = userEvent.setup();
    const { onImageChange } = renderInput({
      image: {
        file: new File(["poster"], "poster.png", { type: "image/png" }),
        name: "poster.png",
        url: "blob:mock-url",
        mimeType: "image/png",
      },
    });

    expect(screen.getByText("poster.png")).toBeInTheDocument();

    await user.click(screen.getByTestId("mockup-image-clear"));

    expect(onImageChange).toHaveBeenCalledWith(null);
  });
});
