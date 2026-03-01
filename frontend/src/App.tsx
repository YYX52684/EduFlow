import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { AuthPage } from "./pages/AuthPage";
import { ConsolePage } from "./pages/ConsolePage";
import { SettingsPage } from "./pages/SettingsPage";
import { WorkspacePage } from "./pages/WorkspacePage";

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

