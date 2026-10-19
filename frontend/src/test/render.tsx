import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";

import { createQueryClient } from "../queryClient";
import { routes } from "../router";
import { createMockBackend, type MockBackendOptions } from "./mockBackend";
import { server } from "./server";

export function setup(path: string, options: MockBackendOptions = {}) {
  const backend = createMockBackend(options);
  server.use(...backend.handlers);
  const queryClient = createQueryClient();
  queryClient.setDefaultOptions({ queries: { ...queryClient.getDefaultOptions().queries, retry: false } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const user = userEvent.setup();
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { ...utils, user, router, backend, queryClient };
}
