import type { RouteObject } from "react-router";

import { ReviewCompletePage } from "./features/complete/ReviewCompletePage";
import { NewReviewPage } from "./features/draft/NewReviewPage";
import { ReviewWorkspacePage } from "./features/review/ReviewWorkspacePage";
import { NotFoundPage } from "./features/NotFoundPage";

export const routes: RouteObject[] = [
  { path: "/", element: <NewReviewPage /> },
  { path: "/review/:projectId", element: <ReviewWorkspacePage /> },
  { path: "/review/:projectId/complete", element: <ReviewCompletePage /> },
  { path: "*", element: <NotFoundPage /> },
];
