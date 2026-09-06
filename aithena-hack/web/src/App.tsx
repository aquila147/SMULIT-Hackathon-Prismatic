import { Routes, Route } from 'react-router-dom'
import { SiteHeader } from './components/site-header'
import HomePage from './pages/HomePage'
import ReportPage from './pages/ReportPage'
import ContractsPage from './pages/ContractsPage'
import ContractDetailPage from './pages/ContractDetailPage'
import CalendarPage from './pages/CalendarPage'
import RisksPage from './pages/RisksPage'
import AskPage from './pages/AskPage'
import HelpPage from './pages/HelpPage'

export default function App() {
  return (
    <>
      <SiteHeader />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/report" element={<ReportPage />} />
        <Route path="/contracts" element={<ContractsPage />} />
        <Route path="/contracts/:id" element={<ContractDetailPage />} />
        <Route path="/calendar" element={<CalendarPage />} />
        <Route path="/risks" element={<RisksPage />} />
        <Route path="/ask" element={<AskPage />} />
        <Route path="/help" element={<HelpPage />} />
      </Routes>
    </>
  )
}
