// Which project to open as CORBELscore starts: one Finder handed over (open-file,
// which can arrive before the app is ready), else one on the command line. macOS
// also adds "-psn_…" when it launches an app from Finder; that is not a project.
export const PROJECT_FILE = /\.(corbel|tsproj|json|tsp)$/i;

export function startFile(queued, argv) {
  return queued.find((f) => PROJECT_FILE.test(f)) ?? argv.find((a) => !a.startsWith("-") && PROJECT_FILE.test(a)) ?? "";
}
