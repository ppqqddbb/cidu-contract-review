import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { App } from "./app";

describe("App", () => {
  it("renders the product shell", () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const html = renderToString(
      <QueryClientProvider client={client}>
        <App />
      </QueryClientProvider>,
    );

    expect(html).toContain("标准合同 AI 预审工作台");
    expect(html).toContain("合同提交");
    expect(html).toContain("合同解析与问题标注");
  });
});
