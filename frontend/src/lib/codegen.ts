import { downloadFile } from "./api";

export const CODEGEN_ACTIONS: Record<string, string> = {
  sql: "sql",
  prisma: "prisma",
  sqlalchemy: "sqlalchemy",
  fastapi: "fastapi",
  express: "express",
  spring: "spring",
  react: "react",
  nextjs: "nextjs",
};

export function isCodegenAction(actionId: string): boolean {
  return actionId in CODEGEN_ACTIONS;
}

export function downloadCodegen(
  projectId: number,
  actionId: string,
  fallbackName: string,
): void {
  const generatorId = CODEGEN_ACTIONS[actionId];
  const safeName = (fallbackName || "project")
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/(^-|-$)/g, "");
  downloadFile(`/projects/${projectId}/codegen/${generatorId}`, `${safeName}-${generatorId}.zip`);
}
