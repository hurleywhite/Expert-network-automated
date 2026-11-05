import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import ProjectDetail from './pages/ProjectDetail';
import ExpertProfile from './pages/ExpertProfile';
import AuthGate from './components/AuthGate';
import Screener from './pages/Screener';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public: the link shared in Reddit posts and emails. Deliberately
            outside AuthGate — respondents have no account. */}
        <Route path="/s/:projectId" element={<Screener />} />

        {/* The admin app sits behind the password gate. */}
        <Route path="/" element={<AuthGate><Dashboard /></AuthGate>} />
        <Route path="/projects/:projectId" element={<AuthGate><ProjectDetail /></AuthGate>} />
        <Route
          path="/projects/:projectId/experts/:expertId"
          element={<AuthGate><ExpertProfile /></AuthGate>}
        />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
