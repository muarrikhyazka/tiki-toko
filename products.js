const WHATSAPP_NUMBER = "628XXXXXXXXXX"; // Ganti dengan nomor WA kamu (format: 628xxx)

const products = [
  {
    id: 1,
    name: "Contoh Produk 1",
    price: 150000,
    description: "Deskripsi singkat produk. Jarang dipakai, kondisi masih bagus. Bisa dicek langsung sebelum beli.",
    imageFolder: "images/produk1",
    images: ["1.jpg", "2.jpg", "3.jpg"],   // nama file foto dalam folder
    ecommerceUrl: "https://tokopedia.com",  // link harga baru (opsional, hapus baris ini kalau tidak ada)
    ecommercePrice: 350000,                 // harga baru di ecommerce (opsional)
  },
  {
    id: 2,
    name: "Contoh Produk 2",
    price: 75000,
    description: "Deskripsi singkat produk. Ada sedikit bekas pakai tapi masih berfungsi dengan baik.",
    imageFolder: "images/produk2",
    images: ["1.jpg"],
    ecommerceUrl: "https://shopee.co.id",
    ecommercePrice: 180000,
  },
  {
    id: 3,
    name: "Contoh Produk 3",
    price: 200000,
    description: "Deskripsi singkat produk. Beli tapi tidak pernah dipakai, masih dalam kondisi seperti baru.",
    imageFolder: "images/produk3",
    images: ["1.jpg", "2.jpg"],
    // tidak ada ecommerceUrl → tidak ditampilkan
  },
];
