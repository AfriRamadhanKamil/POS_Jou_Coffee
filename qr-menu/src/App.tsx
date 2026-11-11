import { useEffect, useMemo, useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import {
  createQrisPayment,
  createQrOrder,
  getErrorMessage,
  getMenu,
  getOrderStatus,
  type MenuItem,
  type Modifier,
  type ModifierGroup,
  type OrderStatus,
  type PublicMenu,
} from './api'
import './App.css'

type CartLine = {
  menu: MenuItem
  variantId: string
  modifierIds: string[]
  quantity: number
}

const currency = new Intl.NumberFormat('id-ID', {
  style: 'currency',
  currency: 'IDR',
  maximumFractionDigits: 0,
})

function readTableToken(): string {
  const pathToken = window.location.pathname.split('/').filter(Boolean)[0]
  return new URLSearchParams(window.location.search).get('token') || pathToken || ''
}

function App() {
  const token = readTableToken()
  const [menu, setMenu] = useState<PublicMenu | null>(null)
  const [loading, setLoading] = useState(Boolean(token))
  const [isOnline, setIsOnline] = useState(navigator.onLine)
  const [loadError, setLoadError] = useState('')
  const [cart, setCart] = useState<CartLine[]>([])
  const [editingMenu, setEditingMenu] = useState<MenuItem | null>(null)
  const [selectedVariant, setSelectedVariant] = useState('')
  const [selectedModifiers, setSelectedModifiers] = useState<string[]>([])
  const [customerName, setCustomerName] = useState('')
  const [orderType, setOrderType] = useState<'DINE_IN' | 'TAKE_AWAY'>('DINE_IN')
  const [paymentMethod, setPaymentMethod] = useState<'TUNAI' | 'QRIS'>('TUNAI')
  const [submitting, setSubmitting] = useState(false)
  const [checkoutError, setCheckoutError] = useState('')
  const [order, setOrder] = useState<OrderStatus | null>(null)
  const [qrisContent, setQrisContent] = useState('')
  const [qrisImageData, setQrisImageData] = useState('')
  const [qrisError, setQrisError] = useState('')
  const [qrisBusy, setQrisBusy] = useState(false)

  useEffect(() => {
    const updateOnline = () => setIsOnline(navigator.onLine)
    window.addEventListener('online', updateOnline)
    window.addEventListener('offline', updateOnline)
    return () => {
      window.removeEventListener('online', updateOnline)
      window.removeEventListener('offline', updateOnline)
    }
  }, [])

  useEffect(() => {
    let active = true
    if (!token) return

    getMenu(token)
      .then((result) => {
        if (active) setMenu(result)
      })
      .catch((error: unknown) => {
        if (active) setLoadError(getErrorMessage(error))
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [token])

  const orderId = order?.id
  const paymentStatus = order?.payment_status
  const orderStatus = order?.status
  useEffect(() => {
    if (
      !orderId ||
      paymentStatus === 'PAID' ||
      orderStatus === 'REJECTED' ||
      orderStatus === 'EXPIRED' ||
      orderStatus === 'CANCELLED'
    ) return
    const timer = window.setInterval(() => {
      getOrderStatus(orderId)
        .then((status) => {
          setOrder(status)
          if (status.payment_status === 'PAID') setQrisError('')
        })
        .catch((error: unknown) => {
          setQrisError(`Status pesanan belum dapat diperbarui. ${getErrorMessage(error)}`)
        })
    }, 5000)
    return () => window.clearInterval(timer)
  }, [orderId, paymentStatus, orderStatus])

  const total = useMemo(
    () =>
      cart.reduce((sum, line) => {
        const variant = line.menu.variants.find((item) => item.id === line.variantId)
        const modifiers =
          menu?.modifier_groups
            .flatMap((group) => group.modifiers)
            .filter((modifier) => line.modifierIds.includes(modifier.id))
            .reduce((sumPrice, modifier) => sumPrice + modifier.price, 0) ?? 0
        return sum + (line.menu.base_price + (variant?.price_adjustment ?? 0) + modifiers) * line.quantity
      }, 0),
    [cart, menu],
  )

  function openMenuOptions(item: MenuItem) {
    setEditingMenu(item)
    setSelectedVariant(item.variants[0]?.id ?? '')
    setSelectedModifiers([])
  }

  function toggleModifier(group: ModifierGroup, modifier: Modifier) {
    setSelectedModifiers((current) => {
      const selected = current.includes(modifier.id)
        ? current.filter((id) => id !== modifier.id)
        : group.max_selection > 0 &&
            current.filter((id) =>
              group.modifiers.some((option) => option.id === id),
            ).length >= group.max_selection
          ? current
          : [...current, modifier.id]
      return selected
    })
  }

  function addItem() {
    if (!editingMenu) return
    const missingRequired = menu?.modifier_groups.some((group) => {
      const count = group.modifiers.filter((modifier) =>
        selectedModifiers.includes(modifier.id),
      ).length
      return group.is_required && count < group.min_selection
    })
    if (missingRequired) {
      setCheckoutError('Pilih opsi yang wajib sebelum menambahkan menu.')
      return
    }

    const line: CartLine = {
      menu: editingMenu,
      variantId: selectedVariant,
      modifierIds: selectedModifiers,
      quantity: 1,
    }
    setCart((current) => {
      const existing = current.find(
        (item) =>
          item.menu.id === line.menu.id &&
          item.variantId === line.variantId &&
          [...item.modifierIds].sort().join(',') === [...line.modifierIds].sort().join(','),
      )
      if (!existing) return [...current, line]
      return current.map((item) =>
        item === existing ? { ...item, quantity: item.quantity + 1 } : item,
      )
    })
    setCheckoutError('')
    setEditingMenu(null)
  }

  function updateQuantity(index: number, delta: number) {
    setCart((current) =>
      current
        .map((item, itemIndex) =>
          itemIndex === index
            ? { ...item, quantity: item.quantity + delta }
            : item,
        )
        .filter((item) => item.quantity > 0),
    )
  }

  async function submitOrder(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!token || !cart.length) return
    if (orderType === 'TAKE_AWAY' && !customerName.trim()) {
      setCheckoutError('Nama untuk dipanggil wajib diisi untuk pesanan Take Away.')
      return
    }
    setSubmitting(true)
    setCheckoutError('')
    setQrisError('')
    try {
      const created = await createQrOrder(token, {
        customer_name: customerName.trim(),
        order_type: orderType,
        payment_method: paymentMethod,
        items: cart.map((line) => ({
          menu_id: line.menu.id,
          item_name: line.menu.name,
          quantity: line.quantity,
          ...(line.variantId ? { variant_id: line.variantId } : {}),
          modifier_ids: line.modifierIds,
        })),
      })
      setCart([])
      const initialOrder: OrderStatus = {
        id: created.order_id,
        order_no: created.order_no,
        status: created.status,
        payment_status: 'UNPAID',
        customer_name: customerName.trim(),
        total: created.total,
      }
      setOrder(initialOrder)
      if (paymentMethod === 'QRIS') {
        try {
          const payment = await createQrisPayment(created.order_id)
          setQrisContent(payment.qris_content ?? '')
          setQrisImageData(payment.qris_image_data ?? '')
        } catch (error) {
          setQrisError(`Pesanan dibuat, tetapi tagihan QRIS belum tersedia. ${getErrorMessage(error)}`)
        }
      }
    } catch (error) {
      setCheckoutError(getErrorMessage(error))
    } finally {
      setSubmitting(false)
    }
  }

  async function retryQrisPayment() {
    if (!order) return
    setQrisBusy(true)
    setQrisError('')
    try {
      const payment = await createQrisPayment(order.id)
      setQrisContent(payment.qris_content ?? '')
      setQrisImageData(payment.qris_image_data ?? '')
    } catch (error) {
      setQrisError(getErrorMessage(error))
    } finally {
      setQrisBusy(false)
    }
  }

  if (!token) {
    return (
      <main className="center-state">
        <div className="state-icon">!</div>
        <h1>QR meja tidak valid</h1>
        <p>Silakan pindai QR meja yang tersedia atau minta bantuan kasir.</p>
      </main>
    )
  }
  if (loading) {
    return <main className="center-state"><span className="spinner" /><p>Memuat menu...</p></main>
  }
  if (loadError || !menu) {
    return (
      <main className="center-state">
        <div className="state-icon">!</div>
        <h1>Menu belum tersedia</h1>
        <p>{loadError || 'Silakan minta bantuan kasir.'}</p>
        <button className="button secondary" onClick={() => window.location.reload()}>Coba lagi</button>
      </main>
    )
  }
  if (order) {
    return (
      <main className="status-page">
        <header className="brand-header"><div className="brand-mark">J</div><div><strong>Jou Coffee</strong><small>Pesanan Meja {menu.table.number}</small></div></header>
        <section className="status-card">
          <div className="state-icon success">✓</div>
          <p className="eyebrow">NOMOR PESANAN</p>
          <h1>{order.order_no}</h1>
          <div className="status-pill">{statusLabel(order.status, order.payment_status)}</div>
          <p className="status-copy">{statusDescription(order.status, order.payment_status, paymentMethod)}</p>
          <strong className="status-total">{currency.format(order.total)}</strong>
          {paymentMethod === 'QRIS' && order.payment_status !== 'PAID' && (qrisContent || qrisImageData) && (
            <div className="qris-box">
              {qrisImageData
                ? <img src={qrisImageData} alt="QRIS pembayaran" />
                : <QRCodeSVG value={qrisContent} size={208} includeMargin />}
              <p>Scan QRIS ini untuk melanjutkan pembayaran.</p>
              <small>Status pembayaran diperbarui otomatis setelah server mengonfirmasi pembayaran.</small>
            </div>
          )}
          {qrisError && <p className="inline-error">{qrisError}</p>}
          {paymentMethod === 'QRIS' && order.payment_status !== 'PAID' && !qrisContent && !qrisImageData && (
            <button className="button secondary wide" disabled={qrisBusy || !isOnline} onClick={retryQrisPayment}>
              {qrisBusy ? 'Menyiapkan tagihan...' : 'Coba buat tagihan QRIS lagi'}
            </button>
          )}
          {order.status === 'REJECTED' && <p className="inline-error">Pesanan ditolak. Silakan hubungi kasir untuk bantuan.</p>}
          <button className="button primary wide" onClick={() => { setOrder(null); setQrisContent(''); setQrisImageData(''); setQrisError('') }}>Kembali ke menu</button>
        </section>
      </main>
    )
  }

  return (
    <div className="page">
      <header className="brand-header">
        <div className="brand-mark">J</div>
        <div><strong>Jou Coffee</strong><small>Menu digital · Meja {menu.table.number}</small></div>
        <span className={`online-indicator ${isOnline ? '' : 'offline'}`}><i /> {isOnline ? 'Online' : 'Offline'}</span>
      </header>
      {!isOnline && <p className="offline-banner">Koneksi terputus. QR menu memerlukan internet; silakan hubungi kasir untuk memesan.</p>}
      <section className="welcome">
        <p className="eyebrow">SELAMAT DATANG</p>
        <h1>Temukan kopi<br />favoritmu.</h1>
        <p>Dibuat dengan sepenuh hati, untuk menemani harimu.</p>
      </section>
      <main className="menu-layout">
        <section className="menu-list">
          {menu.categories.map((category) => (
            <section className="category" key={category.id}>
              <div className="section-heading"><h2>{category.name}</h2><span>{category.menus.length} menu</span></div>
              <div className="menu-grid">
                {category.menus.map((item) => (
                  <article className={`menu-card ${!item.is_available ? 'unavailable' : ''}`} key={item.id}>
                    <div className="menu-art">
                      {item.image_url ? <img src={item.image_url} alt="" loading="lazy" /> : <span>☕</span>}
                      {!item.is_available && <label>Habis</label>}
                    </div>
                    <div className="menu-card-content">
                      <h3>{item.name}</h3>
                      <p>{item.description || (item.variants.length ? `${item.variants.length} pilihan ukuran` : 'Freshly brewed for you')}</p>
                      <div className="menu-card-bottom"><strong>{currency.format(item.base_price)}</strong>
                        <button aria-label={`Pilih ${item.name}`} disabled={!item.is_available} onClick={() => openMenuOptions(item)}>+</button>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ))}
        </section>
        <aside className="checkout-panel">
          <div className="section-heading"><h2>Pesananmu</h2><span>{cart.reduce((sum, item) => sum + item.quantity, 0)} item</span></div>
          {cart.length === 0 ? <div className="empty-cart"><span>🛍</span><p>Keranjangmu masih kosong.</p><small>Pilih menu favorit untuk memulai.</small></div> : (
            <ul className="cart-list">
              {cart.map((line, index) => {
                const variant = line.menu.variants.find((item) => item.id === line.variantId)
                return <li key={`${line.menu.id}-${line.variantId}-${index}`}>
                  <div className="cart-info"><strong>{line.menu.name}</strong><small>{variant?.name || 'Regular'}</small><b>{currency.format(line.menu.base_price + (variant?.price_adjustment ?? 0) + (menu?.modifier_groups.flatMap((group) => group.modifiers).filter((modifier) => line.modifierIds.includes(modifier.id)).reduce((sum, modifier) => sum + modifier.price, 0) ?? 0))}</b></div>
                  <div className="quantity"><button aria-label="Kurangi jumlah" onClick={() => updateQuantity(index, -1)}>−</button><span>{line.quantity}</span><button aria-label="Tambah jumlah" onClick={() => updateQuantity(index, 1)}>+</button></div>
                </li>
              })}
            </ul>
          )}
          <form onSubmit={submitOrder}>
            <label className="field-label" htmlFor="order-type">Pesanan untuk</label>
            <select id="order-type" value={orderType} onChange={(event) => setOrderType(event.target.value as 'DINE_IN' | 'TAKE_AWAY')}>
              <option value="DINE_IN">Makan di tempat · Meja {menu.table.number}</option>
              <option value="TAKE_AWAY">Bawa pulang</option>
            </select>
            {orderType === 'TAKE_AWAY' && <input aria-label="Nama untuk pesanan" placeholder="Nama untuk dipanggil (opsional)" value={customerName} onChange={(event) => setCustomerName(event.target.value)} />}
            <label className="field-label">Metode pembayaran</label>
            <div className="payment-options">
              <button type="button" className={paymentMethod === 'TUNAI' ? 'payment-option active' : 'payment-option'} onClick={() => setPaymentMethod('TUNAI')}><span>💵</span><b>Tunai</b></button>
              <button type="button" className={paymentMethod === 'QRIS' ? 'payment-option active' : 'payment-option'} onClick={() => setPaymentMethod('QRIS')}><span>▦</span><b>QRIS</b></button>
            </div>
            {checkoutError && <p className="inline-error">{checkoutError}</p>}
            <div className="total-row"><span>Total pembayaran</span><strong>{currency.format(total)}</strong></div>
            <button className="button primary wide" disabled={!cart.length || submitting || !isOnline}>
              {submitting ? 'Mengirim pesanan...' : paymentMethod === 'QRIS' ? 'Lanjut ke pembayaran' : 'Pesan sekarang'}
            </button>
            <small className="secure-note">Pembayaran dikonfirmasi oleh sistem Jou Coffee.</small>
          </form>
        </aside>
      </main>
      {editingMenu && <MenuOptionsDialog
        menu={editingMenu}
        groups={menu.modifier_groups}
        selectedVariant={selectedVariant}
        selectedModifiers={selectedModifiers}
        onVariantChange={setSelectedVariant}
        onToggleModifier={toggleModifier}
        onClose={() => setEditingMenu(null)}
        onAdd={addItem}
      />}
    </div>
  )
}

function MenuOptionsDialog({
  menu, groups, selectedVariant, selectedModifiers, onVariantChange,
  onToggleModifier, onClose, onAdd,
}: {
  menu: MenuItem
  groups: ModifierGroup[]
  selectedVariant: string
  selectedModifiers: string[]
  onVariantChange: (id: string) => void
  onToggleModifier: (group: ModifierGroup, modifier: Modifier) => void
  onClose: () => void
  onAdd: () => void
}) {
  const variant = menu.variants.find((item) => item.id === selectedVariant)
  return (
    <div className="dialog-backdrop" role="presentation" onClick={onClose}>
      <section className="options-dialog" role="dialog" aria-modal="true" aria-labelledby="options-title" onClick={(event) => event.stopPropagation()}>
        <button className="dialog-close" aria-label="Tutup" onClick={onClose}>×</button>
        <p className="eyebrow">SESUAIKAN PESANAN</p><h2 id="options-title">{menu.name}</h2>
        {menu.variants.length > 0 && <fieldset><legend>Pilihan ukuran</legend>{menu.variants.map((item) => <label className="choice-row" key={item.id}><input type="radio" name="variant" checked={selectedVariant === item.id} onChange={() => onVariantChange(item.id)} /><span>{item.name}</span><small>{item.price_adjustment > 0 ? `+${currency.format(item.price_adjustment)}` : ''}</small></label>)}</fieldset>}
        {groups.map((group) => <fieldset key={group.id}><legend>{group.name}{group.is_required && <small> · Wajib</small>}</legend>{group.modifiers.map((modifier) => <label className="choice-row" key={modifier.id}><input type="checkbox" checked={selectedModifiers.includes(modifier.id)} onChange={() => onToggleModifier(group, modifier)} /><span>{modifier.name}</span><small>{modifier.price ? `+${currency.format(modifier.price)}` : 'Gratis'}</small></label>)}</fieldset>)}
        <div className="dialog-footer"><strong>{currency.format(menu.base_price + (variant?.price_adjustment ?? 0))}</strong><button className="button primary" onClick={onAdd}>Tambah ke pesanan</button></div>
      </section>
    </div>
  )
}

function statusLabel(status: string, paymentStatus: string): string {
  if (paymentStatus === 'PAID') return 'Pembayaran berhasil'
  if (status === 'PENDING_APPROVAL') return 'Menunggu persetujuan kasir'
  if (status === 'AWAITING_PAYMENT') return 'Menunggu pembayaran'
  if (status === 'APPROVED') return 'Pesanan diterima'
  if (status === 'PREPARING') return 'Sedang disiapkan'
  if (status === 'READY') return 'Pesanan siap'
  if (status === 'COMPLETED') return 'Pesanan selesai'
  return status.replaceAll('_', ' ')
}

function statusDescription(status: string, paymentStatus: string, method: 'TUNAI' | 'QRIS'): string {
  if (paymentStatus === 'PAID') return 'Terima kasih! Pembayaranmu sudah dikonfirmasi.'
  if (status === 'PENDING_APPROVAL' && method === 'TUNAI') return 'Kasir akan memeriksa pesananmu. Silakan bayar tunai di kasir.'
  if (status === 'AWAITING_PAYMENT') return 'Selesaikan pembayaran. Status akan diperbarui setelah pembayaran terverifikasi.'
  if (status === 'READY') return 'Pesananmu sudah siap. Silakan ambil di kasir.'
  if (status === 'PREPARING') return 'Barista kami sedang menyiapkan pesananmu.'
  return 'Pantau halaman ini untuk melihat perkembangan pesanan.'
}

export default App
