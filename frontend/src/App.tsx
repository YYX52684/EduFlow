import { Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ConsolePage } from "./pages/ConsolePage";
import { SettingsPage } from "./pages/SettingsPage";
import { WorkspacePage } from "./pages/WorkspacePage";
import { AuthPage } from "./pages/AuthPage";

const App = () => {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<ConsolePage />} />
        <Route path="/w/:workspaceId" element={<ConsolePage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/workspace" element={<WorkspacePage />} />
        <Route path="/auth" element={<AuthPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
};

export default App;

