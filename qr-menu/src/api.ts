import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 12_000,
})

export type Modifier = {
  id: string
  name: string
  price: number
}

export type ModifierGroup = {
  id: string
  name: string
  min_selection: number
  max_selection: number
  is_required: boolean
  modifiers: Modifier[]
}

export type MenuItem = {
  id: string
  name: string
  description?: string | null
  image_url?: string | null
  base_price: number
  is_available: boolean
  variants: { id: string; name: string; price_adjustment: number }[]
}

export type MenuCategory = {
  id: string
  name: string
  menus: MenuItem[]
}

export type PublicMenu = {
  table: { id: string; number: string; name?: string | null }
  categories: MenuCategory[]
  modifier_groups: ModifierGroup[]
}

export type OrderStatus = {
  id: string
  order_no: string
  status: string
  payment_status: string
  customer_name: string
  total: number
}

export async function getMenu(token: string): Promise<PublicMenu> {
  const { data } = await api.get(`/public/qr/${encodeURIComponent(token)}/menu`)
  return data.data as PublicMenu
}

export async function createQrOrder(
  token: string,
  order: {
    customer_name: string
    order_type: 'DINE_IN' | 'TAKE_AWAY'
    payment_method: 'TUNAI' | 'QRIS'
    items: {
      menu_id: string
      item_name: string
      quantity: number
      variant_id?: string
      modifier_ids: string[]
    }[]
  },
): Promise<{ order_id: string; order_no: string; status: string; total: number }> {
  const { data } = await api.post(
    `/public/qr/${encodeURIComponent(token)}/orders`,
    order,
  )
  return data.data
}

export async function createQrisPayment(orderId: string): Promise<{
  qris_content: string | null
  qris_image_data: string | null
  expires_in_minutes: number
}> {
  const { data } = await api.post(`/public/orders/${orderId}/pay`)
  return data.data
}

export async function getOrderStatus(orderId: string): Promise<OrderStatus> {
  const { data } = await api.get(`/public/orders/${orderId}/status`)
  return data.data
}

export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const responseMessage = error.response?.data?.message
    if (typeof responseMessage === 'string') return responseMessage
    if (!error.response) return 'Koneksi terputus. Periksa internet lalu coba lagi.'
  }
  return 'Terjadi kesalahan. Silakan coba kembali.'
}
