/**
 * The api module's public surface. Features import from here, never from a file path.
 *
 * Implements: AC8, and the spine's source tree (`src/api/` — typed client, TanStack
 * Query hooks).
 */
export { API_BASE_PATH, ApiError, apiFetch } from './client'
export type { ErrorEnvelope } from './client'
export { login, useLogin } from './auth'
export type { Credentials, LoginResponse } from './auth'
export { clearToken, getToken, setToken, SESSION_EXPIRED_EVENT, TOKEN_STORAGE_KEY } from './session'
export { useHealth } from './health'
export type { HealthResponse } from './health'
export { ME_QUERY_KEY, useMe, useUpdateMe } from './me'
export type { DepartmentBrief, MeResponse } from './me'
export {
  DEPARTMENTS_QUERY_KEY,
  useCreateDepartment,
  useDeleteDepartment,
  useDepartments,
  useRenameDepartment,
} from './departments'
export type { Department, Page } from './departments'
export {
  EMPLOYEES_QUERY_KEY,
  useCreateEmployee,
  useDeactivateEmployee,
  useEmployees,
  useUpdateEmployee,
} from './employees'
export type {
  CreateEmployeeInput,
  Employee,
  EmployeeDepartment,
  UpdateEmployeeInput,
} from './employees'
export {
  LEAVE_TYPES_QUERY_KEY,
  useCreateLeaveType,
  useLeaveTypes,
  useUpdateLeaveType,
} from './leaveTypes'
export type {
  CreateLeaveTypeInput,
  LeaveType,
  LeaveTypeCommandResult,
  UpdateLeaveTypeInput,
} from './leaveTypes'
export {
  HOLIDAYS_QUERY_KEY,
  useCreateHoliday,
  useDeleteHoliday,
  useHolidays,
} from './holidays'
export type { CreateHolidayInput, Holiday, HolidayCommandResult } from './holidays'
// A recalculation is its own concept, not a holiday's (Story 2.12): BOTH a holiday change and a
// leave-type policy edit produce one. These live in `recalculation.ts`, mirroring the backend, where
// they live in `services/recalculation.py` and not in `services/holidays.py`.
export { invalidateEverythingARecalculationMoves } from './recalculation'
export type { RecalculationSummary, RefusedPair } from './recalculation'
export { BALANCES_QUERY_KEY, useBalances } from './balances'
export type { Balance } from './balances'
export {
  LEAVE_REQUESTS_QUERY_KEY,
  useApproveLeaveRequest,
  useCancelLeaveRequest,
  useLeaveRequests,
  usePreviewLeaveRequest,
  useRejectLeaveRequest,
  useSubmitLeaveRequest,
} from './leaveRequests'
export type {
  ExcludedDate,
  LeaveRequest,
  LeaveRequestPreview,
  LeaveRequestSubmission,
  PreviewLeaveInput,
  SubmitLeaveInput,
} from './leaveRequests'
export {
  CANCELLATION_REQUESTS_QUERY_KEY,
  useApproveCancellationRequest,
  useCancellationRequests,
  useRaiseCancellationRequest,
  useRejectCancellationRequest,
} from './cancellationRequests'
export type { CancellationRequest } from './cancellationRequests'
export { AUDIT_ENTRIES_QUERY_KEY, useAuditEntries } from './auditEntries'
export type { AuditEntry } from './auditEntries'
export {
  ADMIN_REVIEW_FLAGS_QUERY_KEY,
  useAdminReviewFlags,
} from './adminReviewFlags'
export type { AdminReviewFlag } from './adminReviewFlags'
export { POLICY_CHANGES_QUERY_KEY, usePolicyChanges } from './policyChanges'
export type { PolicyChange } from './policyChanges'
export { queryClient } from './queryClient'
