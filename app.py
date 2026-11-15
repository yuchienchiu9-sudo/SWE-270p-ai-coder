# Name: Yu-Chien Chiu
# Student ID: 56176405
from services.llm_client import generate_code
import gradio as gr




def generate_application(requirements: str) -> str:
    """Generate Python code using Gemini."""
    if not requirements.strip():
        raise gr.Error("Please enter software requirements.")

    try:
        return generate_code(requirements)
    except Exception as exc:
        raise gr.Error(f"Code generation failed: {exc}")


with gr.Blocks(title="SWE 270P AI Coder") as demo:
    gr.Markdown("# SWE 270P - AI Coder")
    gr.Markdown("Multi-Agent AI Coder with MCP")

    requirements = gr.Textbox(
        label="Software Requirements",
        placeholder="Enter QuickDelivery requirements...",
        lines=6
    )

    generate_btn = gr.Button("Generate")

    output = gr.Textbox(
        label="Generated Result",
        lines=8
    )

    generate_btn.click(
        fn=generate_application,
        inputs=requirements,
        outputs=output
    )


if __name__ == "__main__":
    demo.launch()
