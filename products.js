const WHATSAPP_NUMBER = "628XXXXXXXXXX"; // Ganti dengan nomor WA kamu (format: 628xxx)

const products = [
  {
    id: 1,
    name: "Contoh Produk 1",
    brand: "Nike / Air Max 90",           // merk / tipe (opsional)
    price: 150000,
    description: "Deskripsi singkat produk. Jarang dipakai, kondisi masih bagus. Bisa dicek langsung sebelum beli.",
    imageFolder: "images/produk1",
    images: ["1.jpg", "2.jpg", "3.jpg"],  // nama file foto dalam folder
    ecommerceLinks: [                      // satu atau beberapa link (opsional)
      { label: "Tokopedia", url: "https://tokopedia.com" },
      { label: "Shopee", url: "https://shopee.co.id" },
    ],
  },
  {
    id: 2,
    name: "Contoh Produk 2",
    brand: "Samsung / Galaxy S21",
    price: 75000,
    description: "Deskripsi singkat produk. Ada sedikit bekas pakai tapi masih berfungsi dengan baik.",
    imageFolder: "images/produk2",
    images: ["1.jpg"],
    ecommerceLinks: [
      { label: "Tokopedia", url: "https://tokopedia.com" },
    ],
  },
  {
    id: 3,
    name: "Contoh Produk 3",
    // tanpa brand → tidak ditampilkan
    price: 200000,
    description: "Deskripsi singkat produk. Beli tapi tidak pernah dipakai, masih dalam kondisi seperti baru.",
    imageFolder: "images/produk3",
    images: ["1.jpg", "2.jpg"],
    // tanpa ecommerceLinks → tidak ditampilkan
  },
];
