@file:OptIn(ExperimentalSerializationApi::class)

package `in`.anylo.app.core

import kotlinx.serialization.EncodeDefault
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import okhttp3.MultipartBody
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query

// DTOs mirror backend/app/schemas (OpenAPI is the contract). snake_case on the wire.
// kotlinx omits default values, so fields the server must always see carry @EncodeDefault.

@Serializable data class LoginReq(val login: String, val password: String, @EncodeDefault val platform: String = "android", @SerialName("device_label") val deviceLabel: String? = null)
@Serializable data class SignupReq(
    @SerialName("shop_name") val shopName: String, @SerialName("owner_name") val ownerName: String,
    val phone: String, val email: String, val password: String,
    @SerialName("business_type") val businessType: String, @SerialName("state_code") val stateCode: String,
    @EncodeDefault val platform: String = "android",
)
@Serializable data class RefreshReq(@SerialName("refresh_token") val refreshToken: String)
@Serializable data class Tokens(@SerialName("access_token") val accessToken: String, @SerialName("refresh_token") val refreshToken: String? = null)
@Serializable data class ChangePasswordReq(@SerialName("current_password") val current: String, @SerialName("new_password") val new: String, @EncodeDefault val platform: String = "android")

@Serializable data class UserDto(
    val id: String, val email: String, @SerialName("full_name") val fullName: String, val phone: String? = null,
    val role: String, @SerialName("must_change_password") val mustChangePassword: Boolean,
)
@Serializable data class ShopBrief(val id: String, val name: String)
@Serializable data class SubscriptionBrief(val status: String, @SerialName("days_left") val daysLeft: Int? = null, @SerialName("read_only") val readOnly: Boolean)
@Serializable data class Me(
    val user: UserDto, @SerialName("onboarding_completed") val onboardingCompleted: Boolean,
    val shops: List<ShopBrief>, @SerialName("active_shop_id") val activeShopId: String? = null,
    val subscription: SubscriptionBrief? = null, val permissions: List<String>,
)

@Serializable data class Option(val value: String, val label: String)
@Serializable data class Reference(val states: List<Option>, @SerialName("business_types") val businessTypes: List<Option>)

@Serializable data class TaxProfile(
    @SerialName("gst_scheme") val scheme: String, val gstin: String? = null,
    @SerialName("legal_name") val legalName: String? = null,
    @SerialName("prices_include_tax") val pricesIncludeTax: Boolean = true,
)
@Serializable data class Shop(
    val id: String, val name: String, @SerialName("business_type") val businessType: String,
    val phone: String? = null, @SerialName("address_line1") val address: String? = null,
    val city: String? = null, val pincode: String? = null, @SerialName("state_name") val stateName: String,
    @SerialName("upi_vpa") val upi: String? = null, @SerialName("upi_payee_name") val upiPayeeName: String? = null,
    @SerialName("logo_url") val logoUrl: String? = null, val tax: TaxProfile,
)
@Serializable data class ShopPatch(
    val name: String? = null, val phone: String? = null, @SerialName("address_line1") val address: String? = null,
    val city: String? = null, val pincode: String? = null, @SerialName("upi_vpa") val upi: String? = null,
)
@Serializable data class TaxReq(
    @SerialName("gst_scheme") val scheme: String, val gstin: String?, @SerialName("legal_name") val legalName: String?,
    @SerialName("prices_include_tax") val pricesIncludeTax: Boolean,
)

@Serializable data class Staff(
    val id: String, @SerialName("full_name") val fullName: String, val email: String, val role: String,
    @SerialName("is_active") val isActive: Boolean, @SerialName("must_change_password") val mustChangePassword: Boolean,
    @SerialName("temporary_password") val temporaryPassword: String? = null,
)
@Serializable data class StaffReq(@SerialName("full_name") val fullName: String, val email: String, val role: String)
@Serializable data class StaffPatch(@SerialName("is_active") val isActive: Boolean)

@Serializable data class ErrorBody(val detail: JsonElement? = null, val code: String? = null)

interface AnyloApi {
    @POST("auth/login") suspend fun login(@Body b: LoginReq): Tokens
    @POST("auth/signup") suspend fun signup(@Body b: SignupReq): Tokens
    @POST("auth/refresh") suspend fun refresh(@Body b: RefreshReq): Tokens
    @POST("auth/logout") suspend fun logout(@Body b: RefreshReq)
    @POST("auth/password/change") suspend fun changePassword(@Body b: ChangePasswordReq): Tokens
    @GET("auth/me") suspend fun me(): Me
    @GET("meta/reference") suspend fun reference(): Reference

    @GET("shop") suspend fun shop(): Shop
    @PATCH("shop") suspend fun patchShop(@Body b: ShopPatch): Shop
    @PUT("shop/tax-profile") suspend fun putTax(@Body b: TaxReq): Shop
    @POST("shop/onboarding/complete") suspend fun completeOnboarding()
    @Multipart @POST("shop/logo") suspend fun uploadLogo(@Part file: MultipartBody.Part): JsonElement
    @DELETE("shop/logo") suspend fun deleteLogo()

    @GET("shop/staff") suspend fun staff(): List<Staff>
    @POST("shop/staff") suspend fun addStaff(@Body b: StaffReq): Staff
    @PATCH("shop/staff/{id}") suspend fun patchStaff(@Path("id") id: String, @Body b: StaffPatch): Staff
    @POST("shop/staff/{id}/reset-password") suspend fun resetStaff(@Path("id") id: String): Staff
}

// --- catalogue (backend/app/schemas/catalogue.py) ---

@Serializable data class VariantDto(
    val id: String? = null, val name: String? = null, val sku: String? = null, val barcode: String? = null,
    val mrp: String? = null, @SerialName("sale_price") val salePrice: String = "0", @SerialName("cost_price") val costPrice: String = "0",
    @SerialName("reorder_level") val reorderLevel: String = "0", @SerialName("stock_qty") val stockQty: String = "0",
    @SerialName("opening_stock") val openingStock: String? = null,
)
@Serializable data class ProductDto(
    val id: String = "", val name: String, @SerialName("category_id") val categoryId: String? = null,
    @SerialName("category_name") val categoryName: String? = null, val brand: String? = null,
    @SerialName("hsn_code") val hsnCode: String? = null, @SerialName("tax_rate_id") val taxRateId: String? = null,
    @SerialName("tax_rate") val taxRate: String? = null, @SerialName("unit_code") val unitCode: String = "NOS",
    @SerialName("track_stock") val trackStock: Boolean = true, @SerialName("price_includes_tax") val priceIncludesTax: Boolean = true, @SerialName("thumb_url") val thumbUrl: String? = null,
    @SerialName("missing_tax_info") val missingTaxInfo: Boolean = false, val variants: List<VariantDto> = emptyList(),
)
@Serializable data class ProductPage(val items: List<ProductDto>, @SerialName("next_cursor") val nextCursor: String? = null, val total: Int)
@Serializable data class LookupDto(val product: ProductDto, val variant: VariantDto)
@Serializable data class CategoryDto(val id: String, val name: String)
@Serializable data class UnitDto(val code: String, val label: String, @SerialName("allows_decimal") val allowsDecimal: Boolean)
@Serializable data class RateDto(val id: String, val label: String, val rate: String, val kind: String)
@Serializable data class AdjustReq(@SerialName("variant_id") val variantId: String, val mode: String, val qty: String, val kind: String = "adjustment", val reason: String? = null)
@Serializable data class BarcodeDto(val barcode: String)
@Serializable data class SnapDto(@SerialName("identified_name") val identifiedName: String, val matches: List<ProductDto> = emptyList())

interface CatalogueApi {
    @GET("products") suspend fun products(@retrofit2.http.Query("q") q: String?, @retrofit2.http.Query("low_stock") low: Boolean = false, @retrofit2.http.Query("limit") limit: Int = 200): ProductPage
    @GET("products/{id}") suspend fun product(@Path("id") id: String): ProductDto
    @GET("products/lookup") suspend fun lookup(@retrofit2.http.Query("code") code: String): LookupDto
    @POST("products") suspend fun create(@Body b: ProductDto): ProductDto
    @PUT("products/{id}") suspend fun update(@Path("id") id: String, @Body b: ProductDto): ProductDto
    @GET("categories") suspend fun categories(): List<CategoryDto>
    @GET("units") suspend fun units(): List<UnitDto>
    @GET("gst-rates") suspend fun rates(): List<RateDto>
    @POST("stock/adjustments") suspend fun adjust(@Body b: AdjustReq): VariantDto
    @POST("barcodes/generate") suspend fun generateBarcode(): BarcodeDto
    @Multipart @POST("products/snap") suspend fun snap(@Part file: MultipartBody.Part): SnapDto
}

// --- sales (backend/app/schemas/sales.py; receipt model from services/sales.receipt) ---

/** Cart shape shared with web held bills (web/src/features/pos/cart.ts), so a bill held on one device resumes on another. */
@Serializable data class CustomItem(
    val name: String, @SerialName("tax_rate_id") val taxRateId: String? = null,
    @SerialName("hsn_code") val hsnCode: String? = null, @SerialName("unit_code") val unitCode: String = "NOS",
)
@Serializable data class CartLine(
    val key: String, val variantId: String? = null, val custom: CustomItem? = null, val name: String, val variantName: String? = null,
    val unit: String, val qty: String, val unitPrice: String, val salePrice: String, val mrp: String? = null, val rate: String, val inclusive: Boolean,
)
@Serializable data class CartCustomer(val name: String = "", val phone: String = "", val gstin: String = "", val address: String = "")
@Serializable data class CartSnapshot(
    val lines: List<CartLine> = emptyList(), val customer: CartCustomer = CartCustomer(), val b2b: Boolean = false,
    val discountType: String = "flat", val discountValue: String = "", val remarks: String = "",
)

@Serializable data class LineReq(@SerialName("variant_id") val variantId: String? = null, val custom: CustomItem? = null, val qty: String, @SerialName("unit_price") val unitPrice: String)
@Serializable data class CustomerReq(val name: String? = null, val phone: String? = null, val gstin: String? = null, val address: String? = null)
@Serializable data class PaymentReq(val method: String, val amount: String, val reference: String? = null)
@Serializable data class CheckoutReq(
    val lines: List<LineReq>, val customer: CustomerReq? = null, @SerialName("discount_type") val discountType: String? = null,
    @SerialName("discount_value") val discountValue: String = "0", val remarks: String? = null, val payments: List<PaymentReq>,
    @SerialName("idempotency_key") val idempotencyKey: String, @SerialName("approval_pin") val approvalPin: String? = null,
)

@Serializable data class ReceiptShop(val name: String, val address: String = "", val phone: String? = null, val gstin: String? = null, @SerialName("logo_url") val logoUrl: String? = null)
@Serializable data class ReceiptBuyer(val name: String? = null, val phone: String? = null, val gstin: String? = null)
@Serializable data class ReceiptLine(
    val id: String = "", @SerialName("returned_qty") val returnedQty: String = "0", val name: String, @SerialName("variant_name") val variantName: String? = null, val hsn: String? = null, val qty: String, val unit: String,
    @SerialName("unit_price") val unitPrice: String, val discount: String, @SerialName("tax_rate") val taxRate: String, @SerialName("line_total") val lineTotal: String,
)
@Serializable data class TaxRow(val rate: String, val taxable: String, val cgst: String, val sgst: String, val igst: String)
@Serializable data class Totals(
    @SerialName("discount_total") val discountTotal: String, @SerialName("taxable_total") val taxableTotal: String,
    @SerialName("cgst_total") val cgstTotal: String, @SerialName("sgst_total") val sgstTotal: String, @SerialName("igst_total") val igstTotal: String,
    @SerialName("cess_total") val cessTotal: String, @SerialName("round_off") val roundOff: String, @SerialName("grand_total") val grandTotal: String,
    @SerialName("paid_total") val paidTotal: String, @SerialName("due_total") val dueTotal: String,
)
@Serializable data class PaymentLine(val method: String, val amount: String)
@Serializable data class Receipt(
    val id: String, val number: String, val title: String, @SerialName("composition_note") val compositionNote: String? = null,
    val status: String, @SerialName("cancel_reason") val cancelReason: String? = null, @SerialName("issued_at") val issuedAt: String,
    @SerialName("handed_over") val handedOver: Boolean, @SerialName("customer_id") val customerId: String? = null, val shop: ReceiptShop, val buyer: ReceiptBuyer? = null,
    @SerialName("place_of_supply") val placeOfSupply: String, @SerialName("supply_type") val supplyType: String,
    @SerialName("state_tax_label") val stateTaxLabel: String, @SerialName("reverse_charge") val reverseCharge: String,
    val lines: List<ReceiptLine>, @SerialName("tax_summary") val taxSummary: List<TaxRow>, val totals: Totals,
    @SerialName("amount_in_words") val amountInWords: String, val payments: List<PaymentLine>, val remarks: String? = null,
    val footer: String, @SerialName("public_url") val publicUrl: String, @SerialName("upi_due_uri") val upiDueUri: String? = null,
)
@Serializable data class InvoiceRow(
    val id: String, val number: String, @SerialName("issued_at") val issuedAt: String, @SerialName("buyer_name") val buyerName: String? = null,
    @SerialName("buyer_phone") val buyerPhone: String? = null, @SerialName("grand_total") val grandTotal: String,
    @SerialName("due_total") val dueTotal: String, val status: String, val methods: List<String> = emptyList(),
)
@Serializable data class InvoicePage(val items: List<InvoiceRow>, val total: Int, @SerialName("sales_total") val salesTotal: String)
@Serializable data class HeldReq(val label: String, val payload: CartSnapshot)
@Serializable data class HeldDto(val id: String, val label: String, val payload: CartSnapshot, @SerialName("created_by_name") val createdByName: String? = null)
@Serializable data class CancelReq(val reason: String)

interface SalesApi {
    @POST("invoices") suspend fun checkout(@Body b: CheckoutReq): Receipt
    @GET("invoices") suspend fun list(@Query("q") q: String?, @Query("from") from: String?, @Query("to") to: String?): InvoicePage
    @GET("invoices/{id}") suspend fun get(@Path("id") id: String): Receipt
    @POST("invoices/{id}/cancel") suspend fun cancel(@Path("id") id: String, @Body b: CancelReq): Receipt
    @POST("invoices/{id}/handover") suspend fun handover(@Path("id") id: String)
    @GET("held-bills") suspend fun held(): List<HeldDto>
    @POST("held-bills") suspend fun hold(@Body b: HeldReq): HeldDto
    @DELETE("held-bills/{id}") suspend fun unhold(@Path("id") id: String)
}

// --- M4: customers, collections, approvals, returns, cash, expenses, labour, loans (backend/app/schemas/backoffice.py) ---

@Serializable data class CustomerDto(
    val id: String, val name: String? = null, val phone: String? = null, val gstin: String? = null,
    @SerialName("billing_address") val address: String? = null, @SerialName("credit_limit") val creditLimit: String? = null,
    @SerialName("opening_balance") val openingBalance: String = "0", val balance: String = "0",
    val bills: Int? = null, val spent: String? = null, @SerialName("last_visit") val lastVisit: String? = null,
)
@Serializable data class CustomerPage(val items: List<CustomerDto>, val total: Int, @SerialName("due_total") val dueTotal: String)
@Serializable data class LedgerEntry(val at: String, val kind: String, val ref: String? = null, val debit: String, val credit: String, val balance: String)
@Serializable data class LedgerDto(@SerialName("opening_balance") val openingBalance: String, val entries: List<LedgerEntry>, val balance: String)
@Serializable data class CollectReq(val amount: String, val method: String, @SerialName("idempotency_key") val idempotencyKey: String)
@Serializable data class CollectionDto(@SerialName("receipt_no") val receiptNo: String, val amount: String, val status: String, @SerialName("balance_after") val balanceAfter: String)
@Serializable data class ApprovalDto(val id: String, val kind: String, val summary: String, @SerialName("requested_by_name") val requestedBy: String? = null)
@Serializable data class NoteReq(val note: String? = null)
@Serializable data class ReturnLineReq(@SerialName("invoice_line_id") val lineId: String, val qty: String)
@Serializable data class CreditNoteReq(
    @SerialName("invoice_id") val invoiceId: String, val lines: List<ReturnLineReq>, @SerialName("refund_method") val refundMethod: String,
    val restock: Boolean, @SerialName("idempotency_key") val idempotencyKey: String,
)
@Serializable data class CreditNoteDto(val number: String? = null, @SerialName("approval_required") val approvalRequired: Boolean = false)
@Serializable data class CashLine(val direction: String, val label: String, val amount: String)
@Serializable data class DayCloseDto(@SerialName("counted_cash") val counted: String, val difference: String, val status: String)
@Serializable data class CashDayDto(
    @SerialName("opening_cash") val opening: String, @SerialName("cash_in") val cashIn: String, @SerialName("cash_out") val cashOut: String,
    @SerialName("expected_cash") val expected: String, @SerialName("pending_cash") val pending: String, val breakdown: List<CashLine>,
    val close: DayCloseDto? = null,
)
@Serializable data class CloseReq(@SerialName("counted_cash") val counted: String, val note: String? = null)
@Serializable data class ExpenseCategory(val id: String, val name: String, @SerialName("is_system") val isSystem: Boolean = false)
@Serializable data class CategoryReq(val name: String)
@Serializable data class ExpenseDto(val id: String, @SerialName("category_name") val category: String, val amount: String, val method: String, val note: String? = null, @SerialName("occurred_on") val day: String)
@Serializable data class ExpensePage(val items: List<ExpenseDto>, val total: String)
@Serializable data class ExpenseReq(@SerialName("category_id") val categoryId: String?, val amount: String, val method: String, val note: String? = null)
@Serializable data class WorkerDto(
    val id: String, val name: String, @SerialName("wage_type") val wageType: String, @SerialName("daily_wage") val dailyWage: String,
    @SerialName("monthly_wage") val monthlyWage: String, val earned: String, @SerialName("total_paid") val paid: String,
    @SerialName("balance_to_pay") val balance: String, val today: String? = null,
)
@Serializable data class WorkerPage(val items: List<WorkerDto>, @SerialName("balance_to_pay") val balanceToPay: String)
@Serializable data class WorkerReq(
    val name: String, val gender: String, @SerialName("wage_type") val wageType: String,
    @SerialName("daily_wage") val dailyWage: String, @SerialName("monthly_wage") val monthlyWage: String,
)
@Serializable data class AttendanceReq(@SerialName("labourer_id") val workerId: String, val day: String, val status: String)
@Serializable data class LabourPayReq(@SerialName("labourer_id") val workerId: String, val kind: String, @SerialName("cash_amount") val cash: String, @SerialName("upi_amount") val upi: String)
@Serializable data class LoanDto(val id: String, @SerialName("lender_name") val lender: String, val principal: String, val outstanding: String, val status: String)
@Serializable data class LoanPage(val items: List<LoanDto>, val outstanding: String)
@Serializable data class LoanReq(@SerialName("lender_name") val lender: String, val principal: String, @SerialName("received_method") val method: String)
@Serializable data class RepayReq(val amount: String, val method: String)

interface MoneyApi {
    @GET("customers") suspend fun customers(@Query("q") q: String?, @Query("has_due") hasDue: Boolean = false): CustomerPage
    @GET("customers/lookup") suspend fun lookup(@Query("phone") phone: String): List<CustomerDto>
    @GET("customers/{id}") suspend fun customer(@Path("id") id: String): CustomerDto
    @GET("customers/{id}/ledger") suspend fun ledger(@Path("id") id: String): LedgerDto
    @POST("customers/{id}/payments") suspend fun collect(@Path("id") id: String, @Body b: CollectReq): CollectionDto
    @GET("approvals") suspend fun approvals(): List<ApprovalDto>
    @POST("approvals/{id}/approve") suspend fun approve(@Path("id") id: String, @Body b: NoteReq): JsonElement
    @POST("approvals/{id}/reject") suspend fun reject(@Path("id") id: String, @Body b: NoteReq): JsonElement
    @POST("credit-notes") suspend fun creditNote(@Body b: CreditNoteReq): CreditNoteDto
    @GET("cash/today") suspend fun cashToday(): CashDayDto
    @POST("cash/close") suspend fun close(@Body b: CloseReq): CashDayDto
    @GET("expenses/categories") suspend fun expenseCategories(): List<ExpenseCategory>
    @POST("expenses/categories") suspend fun addCategory(@Body b: CategoryReq): ExpenseCategory
    @DELETE("expenses/categories/{id}") suspend fun deleteCategory(@Path("id") id: String)
    @GET("expenses") suspend fun expenses(): ExpensePage
    @POST("expenses") suspend fun addExpense(@Body b: ExpenseReq): ExpenseDto
    @DELETE("expenses/{id}") suspend fun deleteExpense(@Path("id") id: String)
    @GET("labour/workers") suspend fun workers(): WorkerPage
    @POST("labour/workers") suspend fun addWorker(@Body b: WorkerReq): JsonElement
    @POST("labour/attendance") suspend fun mark(@Body b: AttendanceReq): JsonElement
    @POST("labour/payments") suspend fun pay(@Body b: LabourPayReq): JsonElement
    @GET("borrowings") suspend fun loans(): LoanPage
    @POST("borrowings") suspend fun addLoan(@Body b: LoanReq): JsonElement
    @POST("borrowings/{id}/repay") suspend fun repay(@Path("id") id: String, @Body b: RepayReq): JsonElement
}

// --- M5: suppliers, purchases, stock counts (backend/app/schemas/purchasing.py) ---

@Serializable data class SupplierDto(val id: String, val name: String, val phone: String? = null, val balance: String = "0")
@Serializable data class SupplierPage(val items: List<SupplierDto>, val payable: String)
@Serializable data class SupplierReq(val name: String, val phone: String? = null)
@Serializable data class PurchaseRowDto(
    val id: String, @SerialName("supplier_name") val supplierName: String, @SerialName("supplier_invoice_no") val billNo: String? = null,
    @SerialName("grand_total") val total: String, val status: String, @SerialName("created_at") val createdAt: String, val items: Int = 0,
)
@Serializable data class PurchaseRows(val items: List<PurchaseRowDto>)
@Serializable data class PurchaseLineReq(@SerialName("variant_id") val variantId: String, val qty: String, @SerialName("unit_cost") val unitCost: String)
@Serializable data class PaidReq(val method: String, val amount: String)
@Serializable data class PurchaseReq(
    @SerialName("supplier_id") val supplierId: String, @SerialName("supplier_invoice_no") val billNo: String?,
    val lines: List<PurchaseLineReq>, val post: Boolean, val paid: List<PaidReq>, @SerialName("idempotency_key") val idempotencyKey: String,
)
@Serializable data class PurchaseDto(val id: String, val status: String, @SerialName("grand_total") val total: String)
@Serializable data class CountRowDto(val id: String, val name: String, val status: String, val counted: Int, val items: Int)
@Serializable data class CountLineDto(
    @SerialName("variant_id") val variantId: String, val name: String, @SerialName("variant_name") val variantName: String? = null,
    @SerialName("expected_qty") val expected: String, @SerialName("counted_qty") val counted: String? = null,
)
@Serializable data class CountDto(val id: String, val name: String, val status: String, val counted: Int, val lines: List<CountLineDto>, @SerialName("variance_value") val varianceValue: String)
@Serializable data class CountReq(val name: String)
@Serializable data class CountLineReq(@SerialName("variant_id") val variantId: String? = null, val code: String? = null, @SerialName("counted_qty") val counted: String? = null, val add: String? = null)

interface PurchasingApi {
    @GET("suppliers") suspend fun suppliers(): SupplierPage
    @POST("suppliers") suspend fun addSupplier(@Body b: SupplierReq): SupplierDto
    @GET("purchases") suspend fun purchases(): PurchaseRows
    @POST("purchases") suspend fun create(@Body b: PurchaseReq): PurchaseDto
    @GET("stock-counts") suspend fun counts(): List<CountRowDto>
    @POST("stock-counts") suspend fun startCount(@Body b: CountReq): CountDto
    @GET("stock-counts/{id}") suspend fun count(@Path("id") id: String): CountDto
    @POST("stock-counts/{id}/lines") suspend fun countLine(@Path("id") id: String, @Body b: CountLineReq): JsonElement
    @POST("stock-counts/{id}/post") suspend fun postCount(@Path("id") id: String): CountDto
}

// --- M6: reports and goals (backend/app/services/finance) ---

@Serializable data class MetricsDto(
    @SerialName("net_sales") val netSales: String, @SerialName("net_revenue") val netRevenue: String, val cogs: String,
    @SerialName("gross_profit") val grossProfit: String, @SerialName("gross_margin_pct") val grossMarginPct: String,
    val expenses: String, val labour: String, @SerialName("net_profit") val netProfit: String,
    @SerialName("invoices_count") val invoicesCount: Int, @SerialName("avg_bill_value") val avgBillValue: String,
)
@Serializable data class PnlDto(val total: MetricsDto)
@Serializable data class AgeingDto(val totals: Map<String, String>)
@Serializable data class TaxHeads(val taxable: String = "0", val igst: String, val cgst: String, val sgst: String)
@Serializable data class Gstr3bDto(@SerialName("outward_taxable") val outward: TaxHeads, val payable: TaxHeads)
@Serializable data class GoalDto(
    val id: String, val metric: String, val title: String, val target: String, val actual: String, val percent: String,
    @SerialName("elapsed_percent") val elapsedPercent: String, @SerialName("run_rate_needed") val runRateNeeded: String? = null,
    @SerialName("days_left") val daysLeft: Int, val status: String, @SerialName("user_name") val userName: String? = null,
)
@Serializable data class DashboardDto(val current: MetricsDto, val previous: MetricsDto, val goals: List<GoalDto> = emptyList())

interface ReportsApi {
    @GET("dashboard") suspend fun dashboard(@Query("from") from: String, @Query("to") to: String): DashboardDto
    @GET("reports/pnl") suspend fun pnl(@Query("from") from: String, @Query("to") to: String): PnlDto
    @GET("reports/receivables") suspend fun receivables(): AgeingDto
    @GET("reports/gst/gstr3b") suspend fun gstr3b(@Query("period") period: String): Gstr3bDto
    @GET("goals") suspend fun goals(): List<GoalDto>
}
