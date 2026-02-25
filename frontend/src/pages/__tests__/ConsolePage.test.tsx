import { render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { ConsolePage } from "../ConsolePage";

describe("ConsolePage", () => {
  it("渲染基础分段标题", () => {
    render(
      <BrowserRouter>
        <ConsolePage />
      </BrowserRouter>,
    );
    expect(
      screen.getByRole("heading", { level: 2, name: /剧本上传与解析/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: /生成教学卡片/ }),
    ).toBeInTheDocument();
  });
});

