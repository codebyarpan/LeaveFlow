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
export { ME_QUERY_KEY, useMe } from './me'
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
export { queryClient } from './queryClient'
