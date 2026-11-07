package `in`.anylo.app.core

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

// DTOs mirror backend/app/schemas (OpenAPI is the contract). snake_case on the wire.

@Serializable data class LoginReq(val login: String, val password: String, val platform: String = "android", @SerialName("device_label") val deviceLabel: String? = null)
@Serializable data class SignupReq(
    @SerialName("shop_name") val shopName: String, @SerialName("owner_name") val ownerName: String,
    val phone: String, val email: String, val password: String,
    @SerialName("business_type") val businessType: String, @SerialName("state_code") val stateCode: String,
    val platform: String = "android",
)
@Serializable data class RefreshReq(@SerialName("refresh_token") val refreshToken: String)
@Serializable data class Tokens(@SerialName("access_token") val accessToken: String, @SerialName("refresh_token") val refreshToken: String? = null)
@Serializable data class ChangePasswordReq(@SerialName("current_password") val current: String, @SerialName("new_password") val new: String, val platform: String = "android")

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
    @SerialName("upi_vpa") val upi: String? = null, val tax: TaxProfile,
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
