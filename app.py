
# Name: YOUR_NAME
# Student ID: YOUR_STUDENT_ID

import gradio as gr


def generate_application(requirements: str) -> str:
    """Display the received software requirements."""
    return f"Received requirements:\n{requirements}"


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
